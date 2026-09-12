"""The orchestrator: a code-owned workflow around LLM agents.

Planning is an LLM call (Opus). Fan-out, the writer → critic → revise loop,
budgets and event emission are code, so they are testable and auditable.
Each delegation runs a fresh tool-runner: sub-agents never share context.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from fin_research.agents.runtime import AgentResult, AgentRuntime, AgentSpec
from fin_research.agents.toolkits import CriticToolkit, FilingsToolkit, QuantToolkit
from fin_research.schemas import (
    CostLedger,
    Depth,
    Finding,
    FindingList,
    Memo,
    Metric,
    MetricTable,
    ResearchPlan,
    ResearchResult,
    ResearchTask,
    RunEvent,
    Verdict,
)

EventSink = Callable[[RunEvent], None]

DEPTH_POLICY: dict[Depth, dict[str, object]] = {
    Depth.BRIEF: {"effort": "low", "critic": False, "max_revisions": 0},
    Depth.STANDARD: {"effort": "medium", "critic": True, "max_revisions": 1},
    Depth.DEEP: {"effort": "high", "critic": True, "max_revisions": 2},
}


@dataclass
class Orchestrator:
    runtime: AgentRuntime
    roster: dict[str, AgentSpec]  # type: ignore[type-arg]
    filings: FilingsToolkit
    quant: QuantToolkit
    critic: CriticToolkit
    coverage: Callable[[], dict[str, dict[str, int]]]
    on_event: EventSink = lambda _e: None
    max_workers: int = 4
    _events: list[RunEvent] = field(default_factory=list)

    # --- public -----------------------------------------------------------------

    def research(self, ticker: str, question: str, depth: Depth = Depth.STANDARD) -> ResearchResult:
        run_id = uuid.uuid4().hex[:12]
        policy = DEPTH_POLICY[depth]
        cost = CostLedger()
        self._events = []
        self._emit(
            run_id, "orchestrator", "run_started", ticker=ticker, question=question, depth=depth
        )

        plan_res = self._plan(run_id, ticker, question)
        cost = cost.add(plan_res.cost)
        plan = plan_res.output

        findings, metrics, c = self._fan_out(run_id, plan.tasks)
        cost = cost.add(c)

        memo_res = self._write(run_id, ticker, question, findings, metrics, verdict=None)
        cost = cost.add(memo_res.cost)
        memo = memo_res.output

        verdict: Verdict | None = None
        revisions = 0
        if policy["critic"]:
            verdict_res = self._verify(run_id, memo, findings, metrics)
            cost = cost.add(verdict_res.cost)
            verdict = verdict_res.output
            while not verdict.passed and revisions < int(policy["max_revisions"]):  # type: ignore[call-overload]
                revisions += 1
                recheck = [
                    ResearchTask(
                        agent="filings_analyst",
                        task=f"Re-check this claim against the filings and return only "
                        f"citations that support or contradict it: {c.claim}",
                        rationale=f"Critic marked it {c.status}: {c.note}".strip(),
                    )
                    for c in verdict.unsupported
                ]
                new_findings, _, c2 = self._fan_out(run_id, recheck)
                cost = cost.add(c2)
                findings = findings + new_findings
                memo_res = self._write(run_id, ticker, question, findings, metrics, verdict)
                cost = cost.add(memo_res.cost)
                memo = memo_res.output
                verdict_res = self._verify(run_id, memo, findings, metrics)
                cost = cost.add(verdict_res.cost)
                verdict = verdict_res.output
            if not verdict.passed:
                memo = flag_unsupported(memo, verdict)

        self._emit(run_id, "orchestrator", "done", revisions=revisions, cost_usd=cost.cost_usd)
        return ResearchResult(
            run_id=run_id,
            ticker=ticker.upper(),
            question=question,
            depth=depth,
            memo=memo,
            verdict=verdict,
            revisions=revisions,
            cost=cost,
            events=list(self._events),
        )

    # --- steps ------------------------------------------------------------------

    def _plan(self, run_id: str, ticker: str, question: str) -> AgentResult[ResearchPlan]:
        cov = self.coverage().get(ticker.upper(), {})
        msg = (
            f"Ticker: {ticker.upper()}\nQuestion: {question}\n"
            f"Knowledge base coverage for this ticker: {cov or 'none ingested'}"
        )
        self._emit(run_id, "planner", "agent_started")
        res = self.runtime.run(self.roster["planner"], msg, [])
        self._emit(run_id, "planner", "plan", plan=res.output.model_dump(mode="json"))
        return res

    def _fan_out(
        self, run_id: str, tasks: list[ResearchTask]
    ) -> tuple[list[Finding], list[Metric], CostLedger]:
        findings: list[Finding] = []
        metrics: list[Metric] = []
        cost = CostLedger()

        def one(task: ResearchTask) -> AgentResult[FindingList] | AgentResult[MetricTable]:
            self._emit(run_id, task.agent, "agent_started", task=task.task)
            if task.agent == "filings_analyst":
                return self.runtime.run(
                    self.roster["filings_analyst"], task.task, self.filings.tools()
                )
            return self.runtime.run(self.roster["quant_analyst"], task.task, self.quant.tools())

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            results = list(pool.map(one, tasks))

        for task, res in zip(tasks, results, strict=True):
            cost = cost.add(res.cost)
            for tc in res.tool_calls:
                self._emit(run_id, task.agent, "tool_call", tool=tc.name, args=tc.args)
            if isinstance(res.output, FindingList):
                findings.extend(res.output.findings)
                self._emit(run_id, task.agent, "finding", count=len(res.output.findings))
            else:
                metrics.extend(res.output.metrics)
                self._emit(run_id, task.agent, "metrics", count=len(res.output.metrics))
        return findings, metrics, cost

    def _write(
        self,
        run_id: str,
        ticker: str,
        question: str,
        findings: list[Finding],
        metrics: list[Metric],
        verdict: Verdict | None,
    ) -> AgentResult[Memo]:
        self._emit(run_id, "memo_writer", "agent_started")
        res = self.runtime.run(
            self.roster["memo_writer"],
            render_writer_input(ticker, question, findings, metrics, verdict),
            [],
        )
        self._emit(run_id, "memo_writer", "memo", memo=res.output.model_dump(mode="json"))
        return res

    def _verify(
        self, run_id: str, memo: Memo, findings: list[Finding], metrics: list[Metric]
    ) -> AgentResult[Verdict]:
        self._emit(run_id, "critic", "agent_started")
        msg = (
            "Verify every claim in this memo.\n\n"
            f"MEMO:\n{memo.model_dump_json(indent=1)}\n\n"
            f"METRIC IDS AVAILABLE FOR recompute: {[m.id for m in metrics]}"
        )
        res = self.runtime.run(self.roster["critic"], msg, self.critic.tools())
        for tc in res.tool_calls:
            self._emit(run_id, "critic", "tool_call", tool=tc.name, args=tc.args)
        self._emit(run_id, "critic", "verdict", verdict=res.output.model_dump(mode="json"))
        return res

    def _emit(self, run_id: str, agent: str, type_: str, **payload: object) -> None:
        ev = RunEvent(run_id=run_id, agent=agent, type=type_, payload=payload)
        self._events.append(ev)
        self.on_event(ev)


# --- pure helpers ---------------------------------------------------------------


def render_writer_input(
    ticker: str,
    question: str,
    findings: list[Finding],
    metrics: list[Metric],
    verdict: Verdict | None,
) -> str:
    lines = [f"Ticker: {ticker.upper()}", f"Question: {question}", "", "FINDINGS"]
    for i, f in enumerate(findings, start=1):
        cites = "; ".join(
            f"{c.form_type} FY{c.fiscal_year} Item {c.item} "
            f"[{c.char_start}-{c.char_end}]: “{c.quote}”"
            for c in f.citations
        )
        lines.append(f"[F{i}] {f.claim} (confidence {f.confidence:.2f}) — {cites}")
    lines += ["", "METRICS"]
    for m in metrics:
        lines.append(f"[M{m.id}] {m.name} = {m.value:.6g} {m.unit} ({m.period})")
    if verdict is not None:
        lines += ["", "PREVIOUS CRITIC VERDICT — address every flagged claim"]
        for c in verdict.unsupported:
            lines.append(f"- {c.status.upper()}: {c.claim} — {c.note}")
    return "\n".join(lines)


def flag_unsupported(memo: Memo, verdict: Verdict) -> Memo:
    """Mark claims the critic could not support instead of silently dropping them."""
    bad = {c.claim for c in verdict.unsupported}
    sections = [
        s.model_copy(update={"claims": [f"⚠ UNVERIFIED: {c}" if c in bad else c for c in s.claims]})
        for s in memo.sections
    ]
    return memo.model_copy(update={"sections": sections})
