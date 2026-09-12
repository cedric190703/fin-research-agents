"""Shared fixtures: a small in-memory corpus of two fiscal years of one ticker."""

import pytest

from marginalia.knowledge.embeddings import HashingEmbedder
from marginalia.knowledge.store import InMemoryStore
from marginalia.schemas import Chunk


def make_chunk(
    cid: str,
    text: str,
    *,
    ticker: str = "AAPL",
    fiscal_year: int = 2024,
    item: str = "1A",
    level: str = "child",
    parent_id: str | None = None,
    char_start: int = 0,
) -> Chunk:
    return Chunk(
        id=cid,
        filing_id=f"acc-{ticker}-{fiscal_year}",
        accession_no=f"acc-{ticker}-{fiscal_year}",
        form_type="10-K",
        ticker=ticker,
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        item=item,
        level="parent" if level == "parent" else "child",
        parent_id=parent_id,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


CORPUS = [
    make_chunk(
        "p24",
        "Competition is intense in the smartphone market.\nWe depend on Taiwan-based suppliers for advanced chips.\nForeign exchange headwinds reduced revenue.",
        level="parent",
    ),
    make_chunk("c24a", "Competition is intense in the smartphone market.", parent_id="p24"),
    make_chunk(
        "c24b",
        "We depend on Taiwan-based suppliers for advanced chips.",
        parent_id="p24",
        char_start=50,
    ),
    make_chunk(
        "c24c", "Foreign exchange headwinds reduced revenue.", parent_id="p24", char_start=105
    ),
    make_chunk(
        "p23",
        "Competition is intense in the smartphone market.\nWe depend on suppliers for advanced chips.",
        level="parent",
        fiscal_year=2023,
    ),
    make_chunk(
        "c23a",
        "Competition is intense in the smartphone market.",
        parent_id="p23",
        fiscal_year=2023,
    ),
    make_chunk(
        "c23b",
        "We depend on suppliers for advanced chips.",
        parent_id="p23",
        fiscal_year=2023,
        char_start=50,
    ),
    make_chunk(
        "p7",
        "Services revenue grew 13% driven by App Store and advertising. ASC 842 lease adoption had no material impact.",
        level="parent",
        item="7",
    ),
    make_chunk(
        "c7a",
        "Services revenue grew 13% driven by App Store and advertising.",
        parent_id="p7",
        item="7",
    ),
    make_chunk(
        "c7b",
        "ASC 842 lease adoption had no material impact.",
        parent_id="p7",
        item="7",
        char_start=63,
    ),
    make_chunk("msft", "Azure cloud revenue grew 30 percent.", ticker="MSFT", item="7"),
]


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder(dim=128)


@pytest.fixture
def store(embedder: HashingEmbedder) -> InMemoryStore:
    s = InMemoryStore()
    vecs = dict(zip([c.id for c in CORPUS], embedder.embed([c.text for c in CORPUS]), strict=True))
    s.upsert(CORPUS, vecs)
    return s
