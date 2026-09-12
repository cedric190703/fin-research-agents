"""Tool functions handed to each agent, bound to the knowledge base and registry.

Functions carry docstrings because the SDK derives the tool description and
parameter docs from them. All return JSON strings.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fin_research.knowledge.retrieval import HybridRetriever, compare_sections
from fin_research.knowledge.store import ChunkStore, Filters
from fin_research.tools.finance import RATIO_UNITS
from fin_research.tools.provenance import ToolRegistry

FundamentalsLoader = Callable[[str, int], Mapping[str, float]]


def _dumps(obj: object) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


@dataclass
class FilingsToolkit:
    store: ChunkStore
    retriever: HybridRetriever

    def tools(self) -> list[Callable[..., str]]:
        return [self.search_filings, self.read_section, self.compare_sections]

    def search_filings(
        self,
        query: str,
        ticker: str,
        fiscal_years: list[int] | None = None,
        items: list[str] | None = None,
    ) -> str:
        """Hybrid search over SEC filing text. Returns the best passages with citation data.

        Args:
            query: What to look for, in natural language or exact terms (e.g. "ASC 842").
            ticker: Ticker symbol, e.g. AAPL.
            fiscal_years: Restrict to these fiscal years, e.g. [2023, 2024].
            items: Restrict to regulatory items, e.g. ["1A"] for Risk Factors, ["7"] for MD&A.
        """
        filters = Filters(
            ticker=ticker,
            fiscal_years=tuple(fiscal_years or ()),
            items=tuple(items or ()),
        )
        hits = self.retriever.search(query, filters)
        return _dumps(
            [
                {
                    "chunk_id": h.chunk.id,
                    "filing_id": h.chunk.filing_id,
                    "accession_no": h.chunk.accession_no,
                    "form_type": h.chunk.form_type,
                    "fiscal_year": h.chunk.fiscal_year,
                    "item": h.chunk.item,
                    "char_start": h.chunk.char_start,
                    "char_end": h.chunk.char_end,
                    "text": h.chunk.text,
                    "score": round(h.score, 4),
                }
                for h in hits
            ]
        )

    def read_section(self, ticker: str, item: str, fiscal_year: int) -> str:
        """Read one full regulatory Item of a filing (e.g. Item 1A of the FY2024 10-K).

        Args:
            ticker: Ticker symbol.
            item: Regulatory item, e.g. "1A", "7", "7A".
            fiscal_year: Fiscal year of the filing.
        """
        parents = self.store.list_sections(ticker, item, fiscal_year)
        return _dumps(
            [
                {
                    "chunk_id": p.id,
                    "filing_id": p.filing_id,
                    "accession_no": p.accession_no,
                    "form_type": p.form_type,
                    "fiscal_year": p.fiscal_year,
                    "item": p.item,
                    "char_start": p.char_start,
                    "char_end": p.char_end,
                    "text": p.text,
                }
                for p in parents
            ]
        )

    def compare_sections(self, ticker: str, item: str, year_from: int, year_to: int) -> str:
        """Diff one regulatory Item between two fiscal years: added and removed paragraphs.

        Args:
            ticker: Ticker symbol.
            item: Regulatory item, e.g. "1A".
            year_from: Earlier fiscal year.
            year_to: Later fiscal year.
        """
        d = compare_sections(self.store, ticker, item, (year_from, year_to))
        return _dumps({"added": d.added, "removed": d.removed, "unchanged_paragraphs": d.unchanged})


@dataclass
class QuantToolkit:
    registry: ToolRegistry
    load_fundamentals: FundamentalsLoader
    _statements: dict[tuple[str, int], Mapping[str, float]] | None = None

    def tools(self) -> list[Callable[..., str]]:
        return [self.get_fundamentals, self.compute_ratios, self.run_dcf, self.run_comps]

    def _statement(self, ticker: str, fiscal_year: int) -> Mapping[str, float]:
        if self._statements is None:
            self._statements = {}
        key = (ticker.upper(), fiscal_year)
        if key not in self._statements:
            self._statements[key] = self.load_fundamentals(ticker.upper(), fiscal_year)
        return self._statements[key]

    def get_fundamentals(self, ticker: str, fiscal_year: int) -> str:
        """Load a fiscal year's statement line items (revenue, income, debt, cash, cash flow).

        Args:
            ticker: Ticker symbol.
            fiscal_year: Fiscal year, e.g. 2024.
        """
        return _dumps(dict(self._statement(ticker, fiscal_year)))

    def compute_ratios(self, ticker: str, fiscal_year: int) -> str:
        """Compute margins, leverage, coverage, FCF and valuation multiples for a fiscal year.

        Args:
            ticker: Ticker symbol.
            fiscal_year: Fiscal year, e.g. 2024.
        """
        metrics = self.registry.call(
            "compute_ratios",
            units=RATIO_UNITS,
            period=f"FY{fiscal_year}",
            statement=dict(self._statement(ticker, fiscal_year)),
        )
        return _dumps([m.model_dump(mode="json") for m in metrics])

    def run_dcf(
        self,
        ticker: str,
        fiscal_year: int,
        growth_rates: list[float],
        wacc: float,
        terminal_growth: float,
    ) -> str:
        """Discounted cash flow from the fiscal year's free cash flow.

        Args:
            ticker: Ticker symbol.
            fiscal_year: Base fiscal year whose FCF is projected.
            growth_rates: One growth rate per projected year, e.g. [0.08, 0.07, 0.06, 0.05, 0.04].
            wacc: Discount rate, e.g. 0.09.
            terminal_growth: Perpetual growth after the explicit period, e.g. 0.025.
        """
        s = self._statement(ticker, fiscal_year)
        fcf0 = float(s["operating_cash_flow"]) - float(s["capex"])
        metrics = self.registry.call(
            "run_dcf",
            units={"enterprise_value": "USD", "equity_value": "USD", "value_per_share": "USD"},
            period=f"FY{fiscal_year}",
            fcf0=fcf0,
            growth_rates=list(growth_rates),
            wacc=wacc,
            terminal_growth=terminal_growth,
            net_debt=float(s["total_debt"]) - float(s["cash"]),
            shares_outstanding=float(s.get("shares_outstanding", 0)) or None,
        )
        return _dumps([m.model_dump(mode="json") for m in metrics])

    def run_comps(self, ticker: str, fiscal_year: int, peers: list[str]) -> str:
        """Trading multiples versus a peer set (median and quartiles).

        Args:
            ticker: Target ticker symbol.
            fiscal_year: Fiscal year for all statements.
            peers: Peer ticker symbols, e.g. ["MSFT", "GOOGL"].
        """

        def to_comp(s: Mapping[str, float]) -> dict[str, float]:
            mcap = float(s.get("price", 0)) * float(s.get("shares_outstanding", 0))
            return {
                "market_cap": mcap,
                "net_debt": float(s["total_debt"]) - float(s["cash"]),
                "ebitda": float(s["ebitda"]),
                "net_income": float(s["net_income"]),
                "revenue": float(s["revenue"]),
            }

        metrics = self.registry.call(
            "run_comps",
            units={},
            period=f"FY{fiscal_year}",
            target=to_comp(self._statement(ticker, fiscal_year)),
            peers={p: to_comp(self._statement(p, fiscal_year)) for p in peers},
        )
        return _dumps([m.model_dump(mode="json") for m in metrics])


@dataclass
class CriticToolkit:
    filings: FilingsToolkit
    registry: ToolRegistry

    def tools(self) -> list[Callable[..., str]]:
        return [self.filings.search_filings, self.filings.read_section, self.recompute]

    def recompute(self, metric_id: str) -> str:
        """Replay the tool call behind a metric id and return its value.

        Args:
            metric_id: The [M...] id attached to a number in the memo.
        """
        try:
            return _dumps({"metric_id": metric_id, "value": self.registry.recompute(metric_id)})
        except KeyError:
            return _dumps({"metric_id": metric_id, "error": "unknown metric id"})
