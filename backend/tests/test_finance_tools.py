import math

import pytest

from fin_research.tools.finance import (
    compute_ratios,
    dcf_sensitivity,
    default_registry,
    run_comps,
    run_dcf,
)
from fin_research.tools.market import fundamentals_from_companyfacts

STATEMENT = {
    "revenue": 1000.0,
    "gross_profit": 450.0,
    "operating_income": 300.0,
    "net_income": 240.0,
    "ebitda": 350.0,
    "total_debt": 400.0,
    "cash": 100.0,
    "equity": 600.0,
    "interest_expense": 30.0,
    "operating_cash_flow": 320.0,
    "capex": 70.0,
    "shares_outstanding": 100.0,
    "price": 48.0,
}


def test_compute_ratios_core_values():
    r = compute_ratios(STATEMENT)
    assert r["gross_margin"] == pytest.approx(0.45)
    assert r["operating_margin"] == pytest.approx(0.30)
    assert r["net_debt"] == 300.0
    assert r["interest_coverage"] == pytest.approx(10.0)
    assert r["free_cash_flow"] == 250.0
    assert r["market_cap"] == 4800.0
    assert r["enterprise_value"] == 5100.0
    assert r["ev_to_ebitda"] == pytest.approx(5100 / 350)
    assert r["pe"] == pytest.approx(20.0)
    assert r["fcf_yield"] == pytest.approx(250 / 4800)


def test_compute_ratios_missing_item_raises_and_zero_denominator_is_nan():
    with pytest.raises(KeyError):
        compute_ratios({"revenue": 1.0})
    s = dict(STATEMENT, interest_expense=0.0)
    assert math.isnan(compute_ratios(s)["interest_coverage"])


def test_run_dcf_matches_hand_calculation():
    # fcf0=100, one year at 10% growth, wacc 10%, g 2%
    r = run_dcf(
        100.0, [0.10], wacc=0.10, terminal_growth=0.02, net_debt=50.0, shares_outstanding=10
    )
    fcf1 = 110.0
    pv_explicit = fcf1 / 1.1
    terminal = fcf1 * 1.02 / 0.08
    pv_terminal = terminal / 1.1
    assert r["pv_explicit"] == pytest.approx(pv_explicit)
    assert r["pv_terminal"] == pytest.approx(pv_terminal)
    assert r["equity_value"] == pytest.approx(pv_explicit + pv_terminal - 50)
    assert r["value_per_share"] == pytest.approx(r["equity_value"] / 10)


def test_run_dcf_rejects_wacc_below_growth():
    with pytest.raises(ValueError):
        run_dcf(100.0, [0.05], wacc=0.02, terminal_growth=0.03)


def test_dcf_sensitivity_grid_is_monotonic():
    grid = dcf_sensitivity(
        100.0, [0.05] * 5, waccs=[0.08, 0.10, 0.12], terminal_growths=[0.01, 0.02, 0.03]
    )
    assert len(grid) == 3 and all(len(row) == 3 for row in grid)
    # higher WACC → lower value; higher g → higher value
    assert grid[0][0] > grid[1][0] > grid[2][0]
    assert grid[1][0] < grid[1][1] < grid[1][2]


def test_run_comps_median_and_premium():
    target = {"market_cap": 1000, "net_debt": 0, "ebitda": 100, "net_income": 50, "revenue": 500}
    peers = {
        "A": {"market_cap": 800, "net_debt": 0, "ebitda": 100, "net_income": 50, "revenue": 500},
        "B": {"market_cap": 1200, "net_debt": 0, "ebitda": 100, "net_income": 50, "revenue": 500},
        "C": {"market_cap": 1000, "net_debt": 0, "ebitda": 100, "net_income": 50, "revenue": 500},
    }
    r = run_comps(target, peers)
    assert r["target_ev_to_ebitda"] == 10.0
    assert r["peer_median_ev_to_ebitda"] == 10.0
    assert r["premium_to_median_ev_to_ebitda"] == pytest.approx(0.0)
    assert r["peer_q1_pe"] < r["peer_q3_pe"]


def test_registry_attaches_provenance_and_recompute_replays():
    reg = default_registry()
    metrics = reg.call(
        "compute_ratios", units={"gross_margin": "ratio"}, period="FY2024", statement=STATEMENT
    )
    gm = next(m for m in metrics if m.name == "gross_margin")
    assert gm.unit == "ratio" and gm.period == "FY2024"
    assert gm.provenance.tool == "compute_ratios"
    assert gm.provenance.args["statement"] == STATEMENT
    assert reg.recompute(gm.id) == pytest.approx(gm.value)
    # Same inputs → same hash → same id (stable across calls)
    again = reg.call("compute_ratios", units={}, period="FY2024", statement=STATEMENT)
    assert next(m for m in again if m.name == "gross_margin").id == gm.id


def test_fundamentals_from_companyfacts_picks_fy_rows_and_first_matching_concept():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 391035000000},
                            {"fy": 2024, "fp": "Q1", "form": "10-Q", "val": 1},
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [{"fy": 2024, "fp": "FY", "form": "10-K", "val": 999}]}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"fy": 2024, "fp": "FY", "form": "10-K", "val": 93736000000}]}
                },
            }
        }
    }
    out = fundamentals_from_companyfacts(facts, 2024)
    assert out == {"revenue": 391035000000.0, "net_income": 93736000000.0}
