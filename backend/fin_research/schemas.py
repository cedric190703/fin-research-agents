"""Typed contracts shared by every agent boundary.

Every sub-agent returns exactly one of these models; the orchestrator never
sees a transcript, only validated data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Depth(StrEnum):
    BRIEF = "brief"
    STANDARD = "standard"
    DEEP = "deep"


# --- Knowledge base -----------------------------------------------------------


class Citation(BaseModel):
    filing_id: str
    accession_no: str
    form_type: str
    fiscal_year: int
    item: str = Field(description="Regulatory item, e.g. '1A' or '7'")
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    quote: str = Field(description="Verbatim span supporting the claim")


class Chunk(BaseModel):
    id: str
    filing_id: str
    accession_no: str
    form_type: str
    ticker: str
    fiscal_year: int
    fiscal_period: str
    item: str
    level: Literal["parent", "child"]
    parent_id: str | None = None
    text: str
    char_start: int
    char_end: int
    tags: dict[str, object] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float
    rank: int


# --- Agent outputs ------------------------------------------------------------


class Finding(BaseModel):
    claim: str
    citations: list[Citation] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class FindingList(BaseModel):
    findings: list[Finding]
    unanswered: list[str] = Field(
        default_factory=list, description="Sub-questions the corpus could not answer"
    )


class Provenance(BaseModel):
    tool: str
    args: dict[str, object]
    data_as_of: datetime
    hash: str


class Metric(BaseModel):
    id: str
    name: str
    value: float
    unit: str
    period: str
    provenance: Provenance


class MetricTable(BaseModel):
    ticker: str
    metrics: list[Metric]
    notes: list[str] = Field(default_factory=list)


class ResearchTask(BaseModel):
    agent: Literal["filings_analyst", "quant_analyst"]
    task: str
    rationale: str


class ResearchPlan(BaseModel):
    ticker: str
    question: str
    tasks: list[ResearchTask] = Field(min_length=1)


class MemoSection(BaseModel):
    heading: str
    claims: list[str] = Field(
        description="Each entry is one factual sentence. Cite with [F<n>] for findings "
        "and [M<id>] for metrics; never restate a number without its [M] reference."
    )


class Memo(BaseModel):
    ticker: str
    title: str
    thesis: str
    sections: list[MemoSection]
    bull_case: list[str]
    bear_case: list[str]
    disclaimer: Literal["Research support only. Not investment advice."] = (
        "Research support only. Not investment advice."
    )


class ClaimVerdict(BaseModel):
    claim: str
    status: Literal["supported", "unsupported", "needs_update"]
    evidence: list[Citation] = Field(default_factory=list)
    note: str = ""


class Verdict(BaseModel):
    passed: bool
    claims: list[ClaimVerdict]

    @property
    def unsupported(self) -> list[ClaimVerdict]:
        return [c for c in self.claims if c.status != "supported"]


# --- Runs ---------------------------------------------------------------------


class RunEvent(BaseModel):
    run_id: str
    agent: str
    type: Literal[
        "run_started",
        "plan",
        "agent_started",
        "tool_call",
        "finding",
        "metrics",
        "memo",
        "verdict",
        "done",
        "error",
    ]
    payload: dict[str, object] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CostLedger(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: CostLedger) -> CostLedger:
        return CostLedger(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
        )


class ResearchResult(BaseModel):
    run_id: str
    ticker: str
    question: str
    depth: Depth
    memo: Memo
    verdict: Verdict | None
    revisions: int
    cost: CostLedger
    events: list[RunEvent]
