import json

import pytest

from fin_research.agents.orchestrator import Orchestrator, flag_unsupported, render_writer_input
from fin_research.agents.roster import build_roster
from fin_research.agents.runtime import AgentSpec, FakeRuntime, cost_from_usage, load_prompt
from fin_research.agents.toolkits import CriticToolkit, FilingsToolkit, QuantToolkit
from fin_research.config import Settings
from fin_research.knowledge.retrieval import HybridRetriever
from fin_research.schemas import (
    Citation,
    ClaimVerdict,
    Depth,
    Finding,
    FindingList,
    Memo,
    MemoSection,
    MetricTable,
    ResearchPlan,
    ResearchTask,
    Verdict,
)
from fin_research.tools.finance import default_registry
from tests.test_finance_tools import STATEMENT

# --- fixtures -----------------------------------------------------------------


@pytest.fixture
def toolkits(store, embedder):
    filings = FilingsToolkit(store=store, retriever=HybridRetriever(store=store, embedder=embedder))
    registry = default_registry()
    quant = QuantToolkit(registry=registry, load_fundamentals=lambda t, y: STATEMENT)
    critic = CriticToolkit(filings=filings, registry=registry)
    return filings, quant, critic


CIT = Citation(
    filing_id="acc-AAPL-2024",
    accession_no="acc-AAPL-2024",
    form_type="10-K",
    fiscal_year=2024,
    item="1A",
    char_start=50,
    char_end=105,
    quote="We depend on Taiwan-based suppliers for advanced chips.",
)
PLAN = ResearchPlan(
    ticker="AAPL",
    question="q",
    tasks=[
        ResearchTask(agent="filings_analyst", task="supplier risk", rationale="r"),
        ResearchTask(agent="quant_analyst", task="ratios FY2024", rationale="r"),
    ],
)
FINDINGS = FindingList(
    findings=[Finding(claim="Supplier concentration in Taiwan.", citations=[CIT], confidence=0.9)]
)
METRICS = MetricTable(ticker="AAPL", metrics=[])
MEMO = Memo(
    ticker="AAPL",
    title="AAPL memo",
    thesis="t",
    sections=[
        MemoSection(
            heading="Risks",
            claims=["Supplier concentration in Taiwan. [F1]", "Made-up claim. [F2]"],
        )
    ],
    bull_case=["b"],
    bear_case=["b"],
)
PASS = Verdict(
    passed=True,
    claims=[ClaimVerdict(claim="Supplier concentration in Taiwan. [F1]", status="supported")],
)
FAIL = Verdict(
    passed=False,
    claims=[
        ClaimVerdict(claim="Supplier concentration in Taiwan. [F1]", status="supported"),
        ClaimVerdict(claim="Made-up claim. [F2]", status="unsupported", note="no source"),
    ],
)


def make_orchestrator(toolkits, scripts, events=None):
    filings, quant, critic = toolkits
    rt = FakeRuntime(scripts=scripts)
    return (
        Orchestrator(
            runtime=rt,
            roster=build_roster(Settings()),
            filings=filings,
            quant=quant,
            critic=critic,
            coverage=lambda: {"AAPL": {"chunks": 11, "latest_fiscal_year": 2024}},
            on_event=(events.append if events is not None else (lambda e: None)),
        ),
        rt,
    )


# --- toolkits -----------------------------------------------------------------


def test_search_filings_tool_returns_citation_fields(toolkits):
    filings, _, _ = toolkits
    hits = json.loads(filings.search_filings("Taiwan suppliers", "AAPL", fiscal_years=[2024]))
    assert hits and hits[0]["item"] == "1A" and hits[0]["fiscal_year"] == 2024
    assert {"chunk_id", "accession_no", "char_start", "char_end", "text"} <= set(hits[0])


def test_read_and_compare_sections_tools(toolkits):
    filings, _, _ = toolkits
    parents = json.loads(filings.read_section("AAPL", "1A", 2024))
    assert [p["chunk_id"] for p in parents] == ["p24"]
    diff = json.loads(filings.compare_sections("AAPL", "1A", 2023, 2024))
    assert "Foreign exchange headwinds reduced revenue." in diff["added"]


def test_quant_tools_emit_metrics_with_provenance_and_critic_can_recompute(toolkits):
    _, quant, critic = toolkits
    metrics = json.loads(quant.compute_ratios("AAPL", 2024))
    gm = next(m for m in metrics if m["name"] == "gross_margin")
    assert gm["provenance"]["tool"] == "compute_ratios" and gm["unit"] == "ratio"
    assert json.loads(critic.recompute(gm["id"]))["value"] == pytest.approx(0.45)
    assert "error" in json.loads(critic.recompute("nope"))


def test_quant_dcf_and_comps_tools(toolkits):
    _, quant, _ = toolkits
    dcf = json.loads(quant.run_dcf("AAPL", 2024, [0.05, 0.05], 0.09, 0.02))
    assert {m["name"] for m in dcf} >= {"enterprise_value", "equity_value", "value_per_share"}
    comps = json.loads(quant.run_comps("AAPL", 2024, ["MSFT"]))
    assert any(m["name"] == "premium_to_median_ev_to_ebitda" for m in comps)


def test_toolkit_functions_have_docstrings_for_schema_generation(toolkits):
    for kit in toolkits:
        for fn in kit.tools():
            assert fn.__doc__ and "Args:" in fn.__doc__, fn.__name__


# --- runtime ------------------------------------------------------------------


def test_cost_from_usage_uses_pricing_table():
    c = cost_from_usage("claude-opus-5", 1_000_000, 100_000, 500_000)
    assert c.cost_usd == pytest.approx(5.0 + 2.5 + 0.25)
    assert cost_from_usage("unknown-model", 10, 10, 10).cost_usd == 0.0


def test_roster_models_and_prompts():
    roster = build_roster(Settings(), effort="high")
    assert roster["planner"].model == "claude-opus-5"
    assert roster["filings_analyst"].model == "claude-sonnet-5"
    assert roster["filings_analyst"].clear_tool_uses is True
    assert roster["critic"].effort == "high" and roster["filings_analyst"].effort == "medium"
    for name in ("planner", "filings_analyst", "quant_analyst", "memo_writer", "critic"):
        assert len(load_prompt(name)) > 100


def test_fake_runtime_rejects_wrong_output_type():
    rt = FakeRuntime(scripts={"x": [PASS]})
    spec = AgentSpec(name="x", model="m", system="s", output_model=Memo)
    with pytest.raises(TypeError):
        rt.run(spec, "hi", [])


# --- orchestrator -------------------------------------------------------------


def test_standard_run_passes_first_time(toolkits):
    events = []
    orch, rt = make_orchestrator(
        toolkits,
        {
            "planner": [PLAN],
            "filings_analyst": [FINDINGS],
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO],
            "critic": [PASS],
        },
        events,
    )
    result = orch.research("aapl", "q", Depth.STANDARD)
    assert result.ticker == "AAPL" and result.revisions == 0
    assert result.verdict is not None and result.verdict.passed
    assert [n for n, _ in rt.calls] == [
        "planner",
        "filings_analyst",
        "quant_analyst",
        "memo_writer",
        "critic",
    ]
    assert result.cost.cost_usd == pytest.approx(0.05)
    assert events[0].type == "run_started" and events[-1].type == "done"
    assert "plan" in {e.type for e in events} and "verdict" in {e.type for e in events}


def test_brief_run_skips_critic(toolkits):
    orch, rt = make_orchestrator(
        toolkits,
        {
            "planner": [PLAN],
            "filings_analyst": [FINDINGS],
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO],
        },
    )
    result = orch.research("AAPL", "q", Depth.BRIEF)
    assert result.verdict is None
    assert "critic" not in [n for n, _ in rt.calls]


def test_revision_loop_rechecks_unsupported_claims_then_passes(toolkits):
    orch, rt = make_orchestrator(
        toolkits,
        {
            "planner": [PLAN],
            "filings_analyst": [FINDINGS, FINDINGS],  # initial + re-check
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO, MEMO],
            "critic": [FAIL, PASS],
        },
    )
    result = orch.research("AAPL", "q", Depth.DEEP)
    assert result.revisions == 1 and result.verdict.passed
    recheck_msg = rt.calls[[n for n, _ in rt.calls].index("filings_analyst", 2)][1]
    assert "Made-up claim" in recheck_msg
    writer_msgs = [m for n, m in rt.calls if n == "memo_writer"]
    assert (
        "PREVIOUS CRITIC VERDICT" in writer_msgs[1]
        and "PREVIOUS CRITIC VERDICT" not in writer_msgs[0]
    )


def test_revision_loop_is_bounded_and_flags_survivors(toolkits):
    orch, rt = make_orchestrator(
        toolkits,
        {
            "planner": [PLAN],
            "filings_analyst": [FINDINGS] * 3,
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO] * 3,
            "critic": [FAIL] * 3,
        },
    )
    result = orch.research("AAPL", "q", Depth.DEEP)
    assert result.revisions == 2
    assert [n for n, _ in rt.calls].count("critic") == 3
    flagged = result.memo.sections[0].claims
    assert flagged == [
        "Supplier concentration in Taiwan. [F1]",
        "⚠ UNVERIFIED: Made-up claim. [F2]",
    ]
    assert result.memo.disclaimer == "Research support only. Not investment advice."


def test_standard_depth_allows_one_revision(toolkits):
    orch, _rt = make_orchestrator(
        toolkits,
        {
            "planner": [PLAN],
            "filings_analyst": [FINDINGS] * 2,
            "quant_analyst": [METRICS],
            "memo_writer": [MEMO] * 2,
            "critic": [FAIL] * 2,
        },
    )
    result = orch.research("AAPL", "q", Depth.STANDARD)
    assert result.revisions == 1 and not result.verdict.passed


# --- helpers ------------------------------------------------------------------


def test_render_writer_input_numbers_findings_and_metrics():
    from fin_research.tools.finance import default_registry

    reg = default_registry()
    metrics = reg.call(
        "compute_ratios", units={"gross_margin": "ratio"}, period="FY2024", statement=STATEMENT
    )
    text = render_writer_input("aapl", "q", FINDINGS.findings, metrics[:1], FAIL)
    assert "[F1] Supplier concentration in Taiwan." in text
    assert f"[M{metrics[0].id}]" in text and "FY2024" in text
    assert "UNSUPPORTED: Made-up claim. [F2]" in text


def test_flag_unsupported_only_touches_flagged_claims():
    out = flag_unsupported(MEMO, FAIL)
    assert out.sections[0].claims[0] == MEMO.sections[0].claims[0]
    assert out.sections[0].claims[1].startswith("⚠ UNVERIFIED")
    assert MEMO.sections[0].claims[1] == "Made-up claim. [F2]"  # original untouched
