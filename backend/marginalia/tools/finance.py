"""Ratios, DCF and comps. Pure functions over plain dicts so they unit-test without I/O."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from marginalia.tools.provenance import ToolRegistry

Statement = Mapping[str, float]


def _get(s: Statement, key: str) -> float:
    if key not in s:
        raise KeyError(f"Missing line item: {key}")
    return float(s[key])


def _safe_div(a: float, b: float) -> float:
    return a / b if b else math.nan


def compute_ratios(statement: Statement) -> dict[str, float]:
    """Core ratios from one period's line items (all in the same currency unit).

    Expected keys: revenue, gross_profit, operating_income, net_income, ebitda,
    total_debt, cash, equity, interest_expense, operating_cash_flow, capex,
    shares_outstanding, price (optional, enables per-share/yield metrics).
    """
    rev = _get(statement, "revenue")
    out = {
        "gross_margin": _safe_div(_get(statement, "gross_profit"), rev),
        "operating_margin": _safe_div(_get(statement, "operating_income"), rev),
        "net_margin": _safe_div(_get(statement, "net_income"), rev),
        "net_debt": _get(statement, "total_debt") - _get(statement, "cash"),
        "debt_to_equity": _safe_div(_get(statement, "total_debt"), _get(statement, "equity")),
        "interest_coverage": _safe_div(
            _get(statement, "operating_income"), _get(statement, "interest_expense")
        ),
        "free_cash_flow": _get(statement, "operating_cash_flow") - _get(statement, "capex"),
    }
    out["net_debt_to_ebitda"] = _safe_div(out["net_debt"], _get(statement, "ebitda"))
    if "price" in statement and "shares_outstanding" in statement:
        mcap = _get(statement, "price") * _get(statement, "shares_outstanding")
        out["market_cap"] = mcap
        out["enterprise_value"] = mcap + out["net_debt"]
        out["fcf_yield"] = _safe_div(out["free_cash_flow"], mcap)
        out["ev_to_ebitda"] = _safe_div(out["enterprise_value"], _get(statement, "ebitda"))
        out["pe"] = _safe_div(mcap, _get(statement, "net_income"))
    return out


def run_dcf(
    fcf0: float,
    growth_rates: Sequence[float],
    wacc: float,
    terminal_growth: float,
    net_debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> dict[str, float]:
    """Explicit-period DCF with Gordon terminal value.

    fcf0: last reported free cash flow. growth_rates: one per projected year.
    """
    if wacc <= terminal_growth:
        raise ValueError("WACC must exceed terminal growth")
    fcfs = []
    fcf = fcf0
    for g in growth_rates:
        fcf *= 1 + g
        fcfs.append(fcf)
    years = np.arange(1, len(fcfs) + 1)
    discount = (1 + wacc) ** years
    pv_explicit = float(np.sum(np.array(fcfs) / discount))
    terminal = fcfs[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = float(terminal / discount[-1])
    ev = pv_explicit + pv_terminal
    out = {
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_terminal,
        "enterprise_value": ev,
        "equity_value": ev - net_debt,
        "terminal_share_of_ev": _safe_div(pv_terminal, ev),
    }
    if shares_outstanding:
        out["value_per_share"] = out["equity_value"] / shares_outstanding
    return out


def dcf_sensitivity(
    fcf0: float,
    growth_rates: Sequence[float],
    waccs: Sequence[float],
    terminal_growths: Sequence[float],
    net_debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> list[list[float]]:
    """WACC × g grid of value per share (or equity value when no share count)."""
    key = "value_per_share" if shares_outstanding else "equity_value"
    grid: list[list[float]] = []
    for w in waccs:
        row = []
        for g in terminal_growths:
            try:
                row.append(run_dcf(fcf0, growth_rates, w, g, net_debt, shares_outstanding)[key])
            except ValueError:
                row.append(math.nan)
        grid.append(row)
    return grid


def run_comps(
    target: Mapping[str, float], peers: Mapping[str, Mapping[str, float]]
) -> dict[str, float]:
    """Trading multiples for the target vs peer median / quartiles.

    Each entry needs: market_cap, net_debt, ebitda, net_income, revenue.
    """

    def multiples(m: Mapping[str, float]) -> dict[str, float]:
        ev = m["market_cap"] + m["net_debt"]
        return {
            "ev_to_ebitda": _safe_div(ev, m["ebitda"]),
            "ev_to_sales": _safe_div(ev, m["revenue"]),
            "pe": _safe_div(m["market_cap"], m["net_income"]),
        }

    t = multiples(target)
    peer_mult = [multiples(p) for p in peers.values()]
    out: dict[str, float] = {}
    for k, v in t.items():
        vals = np.array([pm[k] for pm in peer_mult if not math.isnan(pm[k])])
        out[f"target_{k}"] = v
        if vals.size:
            out[f"peer_median_{k}"] = float(np.median(vals))
            out[f"peer_q1_{k}"] = float(np.percentile(vals, 25))
            out[f"peer_q3_{k}"] = float(np.percentile(vals, 75))
            out[f"premium_to_median_{k}"] = _safe_div(v, float(np.median(vals))) - 1
    return out


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("compute_ratios", compute_ratios)
    reg.register("run_dcf", run_dcf)
    reg.register("run_comps", run_comps)
    return reg
