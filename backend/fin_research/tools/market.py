"""Thin market/macro data adapters. Kept separate so the finance math stays pure.

These hit the network; they are exercised in integration, not unit tests.
"""

from __future__ import annotations

from datetime import date

import httpx

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
XBRL_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"

# us-gaap concepts we map onto the statement keys `compute_ratios` expects.
GAAP_MAP = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "total_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "equity": ["StockholdersEquity"],
    "interest_expense": ["InterestExpense"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "shares_outstanding": ["CommonStockSharesOutstanding"],
}


def fundamentals_from_companyfacts(
    facts: dict[str, object], fiscal_year: int, form: str = "10-K"
) -> dict[str, float]:
    """Pick one value per statement key from an EDGAR companyfacts payload."""
    gaap = facts.get("facts", {})
    gaap = gaap.get("us-gaap", {}) if isinstance(gaap, dict) else {}
    out: dict[str, float] = {}
    for key, concepts in GAAP_MAP.items():
        for concept in concepts:
            node = gaap.get(concept) if isinstance(gaap, dict) else None
            if not isinstance(node, dict):
                continue
            units = node.get("units", {})
            for _unit, rows in units.items():
                for row in rows:
                    if (
                        row.get("fy") == fiscal_year
                        and row.get("form") == form
                        and row.get("fp") == "FY"
                    ):
                        out[key] = float(row["val"])
            if key in out:
                break
    return out


class FredClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=30.0)

    def series(self, series_id: str, start: date, end: date) -> list[tuple[str, float]]:
        resp = self._client.get(
            FRED_URL,
            params={
                "series_id": series_id,
                "api_key": self._key,
                "file_type": "json",
                "observation_start": start.isoformat(),
                "observation_end": end.isoformat(),
            },
        ).raise_for_status()
        return [
            (o["date"], float(o["value"]))
            for o in resp.json()["observations"]
            if o["value"] not in (".", "")
        ]
