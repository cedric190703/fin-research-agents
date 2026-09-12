import json

import httpx
import respx

from marginalia.ingestion.chunking import ChunkSpec, chunk_section, estimate_tokens
from marginalia.ingestion.clean import clean_html
from marginalia.ingestion.edgar import SUBMISSIONS_URL, EdgarClient, FilingRef, parse_submissions
from marginalia.ingestion.pipeline import build_chunks
from marginalia.ingestion.sections import split_sections

# --- edgar --------------------------------------------------------------------

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["10-K", "4", "10-Q", "8-K"],
            "accessionNumber": [
                "0000320193-24-000123",
                "x",
                "0000320193-24-000081",
                "0000320193-24-000050",
            ],
            "filingDate": ["2024-11-01", "2024-10-01", "2024-08-02", "2024-05-03"],
            "reportDate": ["2024-09-28", "", "2024-06-29", "2024-05-02"],
            "primaryDocument": ["aapl-20240928.htm", "f4.xml", "aapl-20240629.htm", "aapl-8k.htm"],
        }
    }
}


def test_parse_submissions_filters_forms_and_limits():
    refs = parse_submissions(
        SUBMISSIONS, ticker="aapl", cik=320193, forms={"10-K", "10-Q"}, limit=5
    )
    assert [r.form_type for r in refs] == ["10-K", "10-Q"]
    assert refs[0].ticker == "AAPL"
    assert refs[0].fiscal_year == 2024
    assert refs[0].fiscal_period == "FY"
    assert refs[1].fiscal_period == "Q2"


def test_filing_ref_document_url_strips_dashes():
    ref = FilingRef(
        320193, "AAPL", "10-K", "0000320193-24-000123", "2024-11-01", "2024-09-28", "a.htm"
    )
    assert (
        ref.document_url
        == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/a.htm"
    )


@respx.mock
def test_edgar_client_sends_user_agent():
    route = respx.get(SUBMISSIONS_URL.format(cik=320193)).mock(
        return_value=httpx.Response(200, content=json.dumps(SUBMISSIONS))
    )
    client = EdgarClient(user_agent="Test bot test@example.com")
    refs = client.list_filings("AAPL", 320193, forms={"8-K"})
    assert len(refs) == 1
    assert route.calls[0].request.headers["User-Agent"] == "Test bot test@example.com"


# --- clean --------------------------------------------------------------------

HTML = """
<html><head><style>p{}</style></head><body>
<p>Item&nbsp;1A.   Risk Factors</p>
<div>We   face intense competition.</div>
<table><tr><th>Year</th><th>Revenue</th></tr><tr><td>2024</td><td>391,035</td></tr></table>
<p>Item 7. Management's Discussion</p>
</body></html>
"""


def test_clean_html_extracts_tables_and_normalises_whitespace():
    doc = clean_html(HTML)
    assert "Item 1A. Risk Factors" in doc.text
    assert "We face intense competition." in doc.text
    assert "391,035" not in doc.text
    assert doc.tables == ["Year | Revenue\n2024 | 391,035"]


# --- sections -----------------------------------------------------------------


def make_filing_text() -> str:
    toc = "Item 1. Business\nItem 1A. Risk Factors\nItem 7. MD&A\n"
    body = (
        "Item 1. Business\n" + "We design products. " * 60 + "\n"
        "Item 1A. Risk Factors\n" + "Competition is intense. " * 60 + "\n"
        "ITEM 7 — Management's Discussion and Analysis\n" + "Revenue grew. " * 60
    )
    return toc + body


def test_split_sections_prefers_body_over_table_of_contents():
    sections = split_sections(make_filing_text())
    items = [s.item for s in sections]
    assert items == ["1", "1A", "7"]
    risk = next(s for s in sections if s.item == "1A")
    assert risk.text.count("Competition is intense.") == 60
    assert "Revenue grew" not in risk.text
    assert risk.title.startswith("Risk Factors")


def test_split_sections_falls_back_to_whole_document():
    sections = split_sections("No items here at all.")
    assert len(sections) == 1 and sections[0].item == "FULL"


# --- chunking -----------------------------------------------------------------


def test_chunk_section_children_cover_parent_and_offsets_resolve():
    text = " ".join(f"w{i}" for i in range(3000))
    spec = ChunkSpec(child_tokens=130, child_overlap=13, parent_tokens=650)
    chunks = chunk_section(text, id_prefix="t", spec=spec)
    parents = [c for c in chunks if c.level == "parent"]
    children = [c for c in chunks if c.level == "child"]
    assert parents and children
    for c in chunks:
        assert text[c.char_start : c.char_end] == c.text
    for p in parents:
        kids = [c for c in children if c.parent_id == p.id]
        assert kids[0].char_start == p.char_start
        assert kids[-1].char_end == p.char_end
        assert all(p.char_start <= k.char_start and k.char_end <= p.char_end for k in kids)
    # overlap: consecutive children share words
    assert children[1].char_start < children[0].char_end


def test_chunk_ids_are_deterministic():
    a = chunk_section("one two three", id_prefix="x")
    b = chunk_section("one two three", id_prefix="x")
    assert [c.id for c in a] == [c.id for c in b]
    assert chunk_section("one two three", id_prefix="y")[0].id != a[0].id


def test_estimate_tokens_scales_with_words():
    assert estimate_tokens("a b c d e f g h i j") == 13


# --- pipeline -----------------------------------------------------------------


def test_build_chunks_carries_filing_metadata_and_absolute_offsets():
    ref = FilingRef(
        320193, "AAPL", "10-K", "0000320193-24-000123", "2024-11-01", "2024-09-28", "a.htm"
    )
    html = "<html><body><p>" + make_filing_text().replace("\n", "</p><p>") + "</p></body></html>"
    chunks = build_chunks(ref, html)
    assert {c.item for c in chunks} == {"1", "1A", "7"}
    assert all(c.ticker == "AAPL" and c.fiscal_year == 2024 for c in chunks)
    full_text = clean_html(html).text
    for c in chunks:
        assert full_text[c.char_start : c.char_end] == c.text
