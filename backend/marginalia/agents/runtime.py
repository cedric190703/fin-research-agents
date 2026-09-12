"""Agent runtime: one place that talks to Claude.

An `AgentSpec` says which model, prompt, effort and output schema an agent has.
`AnthropicRuntime.run` executes one agent to completion with the SDK tool
runner and returns a validated Pydantic object plus cost and a tool-call trace.
`FakeRuntime` returns canned outputs so the orchestrator is testable offline.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from marginalia.schemas import CostLedger

T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# USD per million tokens (input, output, cache read). Kept in code so cost is
# reproducible from a trace; update alongside model changes.
PRICING: dict[str, tuple[float, float, float]] = {
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text().strip()


@dataclass(frozen=True)
class AgentSpec[T: BaseModel]:
    name: str
    model: str
    system: str
    output_model: type[T]
    effort: str = "medium"
    max_turns: int = 12
    max_tokens: int = 16000
    clear_tool_uses: bool = False


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class AgentResult[T: BaseModel]:
    output: T
    cost: CostLedger
    tool_calls: list[ToolCall] = field(default_factory=list)
    turns: int = 0


class AgentRuntime(Protocol):
    def run(
        self, spec: AgentSpec[T], user_message: str, tools: Sequence[Callable[..., str]]
    ) -> AgentResult[T]: ...


def cost_from_usage(
    model: str, input_tokens: int, output_tokens: int, cache_read: int
) -> CostLedger:
    p_in, p_out, p_cache = PRICING.get(model, (0.0, 0.0, 0.0))
    usd = (input_tokens * p_in + output_tokens * p_out + cache_read * p_cache) / 1_000_000
    return CostLedger(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cost_usd=round(usd, 6),
    )


class AnthropicRuntime:
    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client

    def run(
        self, spec: AgentSpec[T], user_message: str, tools: Sequence[Callable[..., str]]
    ) -> AgentResult[T]:
        from anthropic import beta_tool

        runner_tools = [beta_tool(fn) for fn in tools]
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "max_tokens": spec.max_tokens,
            "max_iterations": spec.max_turns,
            # Stable prefix first: frozen system prompt gets the cache breakpoint;
            # the volatile task lives only in the first user message.
            "system": [
                {"type": "text", "text": spec.system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": user_message}],
            "tools": runner_tools,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": spec.effort},
            "output_format": spec.output_model,
            # Route policy refusals to a fallback model server-side.
            "fallbacks": "default",
            "betas": ["server-side-fallback-2026-07-01"],
        }
        if spec.clear_tool_uses:
            kwargs["context_management"] = {"edits": [{"type": "clear_tool_uses_20250919"}]}
            kwargs["betas"].append("context-management-2025-06-27")

        runner = self._client.beta.messages.tool_runner(**kwargs)

        cost = CostLedger()
        calls: list[ToolCall] = []
        turns = 0
        last = None
        for message in runner:
            turns += 1
            last = message
            u = message.usage
            cost = cost.add(
                cost_from_usage(
                    spec.model,
                    getattr(u, "input_tokens", 0) or 0,
                    getattr(u, "output_tokens", 0) or 0,
                    getattr(u, "cache_read_input_tokens", 0) or 0,
                )
            )
            for block in message.content:
                if getattr(block, "type", None) == "tool_use":
                    raw = block.input
                    args = raw if isinstance(raw, dict) else json.loads(str(raw))
                    calls.append(ToolCall(name=block.name, args=dict(args)))
        if last is None:
            raise RuntimeError(f"{spec.name}: no response from model")
        if last.stop_reason == "refusal":
            raise RuntimeError(f"{spec.name}: model refused the request")
        parsed = getattr(last, "parsed_output", None)
        if parsed is None:
            text = "".join(getattr(b, "text", "") for b in last.content if b.type == "text")
            parsed = spec.output_model.model_validate_json(text)
        return AgentResult(output=parsed, cost=cost, tool_calls=calls, turns=turns)


@dataclass
class FakeRuntime:
    """Returns scripted outputs per agent name, in order. Records every call."""

    scripts: dict[str, list[BaseModel]]
    cost_per_call: CostLedger = field(
        default_factory=lambda: CostLedger(input_tokens=100, output_tokens=50, cost_usd=0.01)
    )
    calls: list[tuple[str, str]] = field(default_factory=list)

    def run(
        self, spec: AgentSpec[T], user_message: str, tools: Sequence[Callable[..., str]]
    ) -> AgentResult[T]:
        self.calls.append((spec.name, user_message))
        queue = self.scripts.get(spec.name)
        if not queue:
            raise RuntimeError(f"FakeRuntime: no scripted output left for {spec.name}")
        out = queue.pop(0)
        if not isinstance(out, spec.output_model):
            raise TypeError(f"Scripted output for {spec.name} is not {spec.output_model.__name__}")
        return AgentResult(output=out, cost=self.cost_per_call, tool_calls=[], turns=1)
