"""The agent roster: who runs on which model, with which prompt and output contract."""

from __future__ import annotations

from marginalia.agents.runtime import AgentSpec, load_prompt
from marginalia.config import Settings
from marginalia.schemas import FindingList, Memo, MetricTable, ResearchPlan, Verdict


def build_roster(settings: Settings, effort: str = "medium") -> dict[str, AgentSpec]:  # type: ignore[type-arg]
    """Effort applies to the judging agents; the reading agents stay at medium."""
    return {
        "planner": AgentSpec(
            name="planner",
            model=settings.orchestrator_model,
            system=load_prompt("planner"),
            output_model=ResearchPlan,
            effort=effort,
            max_turns=1,
        ),
        "filings_analyst": AgentSpec(
            name="filings_analyst",
            model=settings.analyst_model,
            system=load_prompt("filings_analyst"),
            output_model=FindingList,
            effort="medium",
            max_turns=settings.subagent_max_turns,
            clear_tool_uses=True,
        ),
        "quant_analyst": AgentSpec(
            name="quant_analyst",
            model=settings.analyst_model,
            system=load_prompt("quant_analyst"),
            output_model=MetricTable,
            effort="medium",
            max_turns=settings.subagent_max_turns,
        ),
        "memo_writer": AgentSpec(
            name="memo_writer",
            model=settings.writer_model,
            system=load_prompt("memo_writer"),
            output_model=Memo,
            effort=effort,
            max_turns=1,
        ),
        "critic": AgentSpec(
            name="critic",
            model=settings.critic_model,
            system=load_prompt("critic"),
            output_model=Verdict,
            effort=effort,
            max_turns=settings.subagent_max_turns,
        ),
    }
