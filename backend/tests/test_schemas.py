import pytest
from pydantic import ValidationError

from fin_research.schemas import (
    Citation,
    ClaimVerdict,
    CostLedger,
    Finding,
    Memo,
    Verdict,
)


def make_citation(**overrides) -> Citation:
    base = dict(
        filing_id="f1",
        accession_no="0000320193-24-000123",
        form_type="10-K",
        fiscal_year=2024,
        item="1A",
        char_start=10,
        char_end=120,
        quote="We face intense competition.",
    )
    base.update(overrides)
    return Citation(**base)


def test_finding_requires_at_least_one_citation():
    with pytest.raises(ValidationError):
        Finding(claim="x", citations=[], confidence=0.9)


def test_finding_confidence_bounded():
    with pytest.raises(ValidationError):
        Finding(claim="x", citations=[make_citation()], confidence=1.5)


def test_memo_disclaimer_is_fixed_literal():
    memo = Memo(ticker="AAPL", title="t", thesis="th", sections=[], bull_case=[], bear_case=[])
    assert memo.disclaimer == "Research support only. Not investment advice."
    with pytest.raises(ValidationError):
        Memo(
            ticker="AAPL",
            title="t",
            thesis="th",
            sections=[],
            bull_case=[],
            bear_case=[],
            disclaimer="Buy now!",  # type: ignore[arg-type]
        )


def test_verdict_unsupported_filters_non_supported():
    v = Verdict(
        passed=False,
        claims=[
            ClaimVerdict(claim="a", status="supported"),
            ClaimVerdict(claim="b", status="unsupported"),
            ClaimVerdict(claim="c", status="needs_update"),
        ],
    )
    assert [c.claim for c in v.unsupported] == ["b", "c"]


def test_cost_ledger_add_is_immutable_and_rounded():
    a = CostLedger(input_tokens=10, output_tokens=5, cost_usd=0.1234567)
    b = CostLedger(input_tokens=1, cache_read_tokens=7, cost_usd=0.0000004)
    c = a.add(b)
    assert (c.input_tokens, c.output_tokens, c.cache_read_tokens) == (11, 5, 7)
    assert c.cost_usd == 0.123457
    assert a.input_tokens == 10
