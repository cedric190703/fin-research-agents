"""Minimal SEC EDGAR client.

EDGAR is free but requires a descriptive User-Agent and asks for ≤10 req/s.
Only the two endpoints we need are wrapped: the company submissions index and
the primary document of a filing.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

SUPPORTED_FORMS = {"10-K", "10-Q", "8-K", "DEF 14A"}


@dataclass(frozen=True)
class FilingRef:
    cik: int
    ticker: str
    form_type: str
    accession_no: str
    filed_at: str  # ISO date
    report_date: str  # ISO date, fiscal period end
    primary_doc: str

    @property
    def fiscal_year(self) -> int:
        return int(self.report_date[:4])

    @property
    def fiscal_period(self) -> str:
        if self.form_type == "10-K":
            return "FY"
        month = int(self.report_date[5:7])
        return f"Q{(month - 1) // 3 + 1}"

    @property
    def document_url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.cik, acc_nodash=self.accession_no.replace("-", ""), doc=self.primary_doc
        )


class EdgarClient:
    def __init__(self, user_agent: str, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
            follow_redirects=True,
        )

    def resolve_cik(self, ticker: str) -> int:
        data = self._client.get(TICKERS_URL).raise_for_status().json()
        wanted = ticker.upper()
        for entry in data.values():
            if entry["ticker"].upper() == wanted:
                return int(entry["cik_str"])
        raise LookupError(f"Ticker {ticker!r} not found on EDGAR")

    def list_filings(
        self, ticker: str, cik: int, forms: set[str] | None = None, limit: int = 12
    ) -> list[FilingRef]:
        forms = forms or SUPPORTED_FORMS
        data = self._client.get(SUBMISSIONS_URL.format(cik=cik)).raise_for_status().json()
        return parse_submissions(data, ticker=ticker, cik=cik, forms=forms, limit=limit)

    def fetch_document(self, ref: FilingRef) -> str:
        return self._client.get(ref.document_url).raise_for_status().text


def parse_submissions(
    data: dict[str, object], *, ticker: str, cik: int, forms: set[str], limit: int
) -> list[FilingRef]:
    """Turn EDGAR's column-oriented `recent` block into FilingRef rows."""
    filings = data.get("filings")
    if not isinstance(filings, dict):
        return []
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        return []
    rows = zip(
        recent["form"],
        recent["accessionNumber"],
        recent["filingDate"],
        recent["reportDate"],
        recent["primaryDocument"],
        strict=True,
    )
    out: list[FilingRef] = []
    for form, acc, filed, report, doc in rows:
        if form not in forms or not report:
            continue
        out.append(
            FilingRef(
                cik=cik,
                ticker=ticker.upper(),
                form_type=form,
                accession_no=acc,
                filed_at=filed,
                report_date=report,
                primary_doc=doc,
            )
        )
        if len(out) >= limit:
            break
    return out
