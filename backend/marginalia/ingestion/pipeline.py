"""Glue: FilingRef → clean → sections → chunks, as `Chunk` rows ready for the store."""

from __future__ import annotations

from collections.abc import Iterable

from marginalia.ingestion.chunking import ChunkSpec, chunk_section
from marginalia.ingestion.clean import clean_html
from marginalia.ingestion.edgar import FilingRef
from marginalia.ingestion.sections import split_sections
from marginalia.schemas import Chunk


def build_chunks(ref: FilingRef, html: str, spec: ChunkSpec | None = None) -> list[Chunk]:
    spec = spec or ChunkSpec()
    doc = clean_html(html)
    out: list[Chunk] = []
    for section in split_sections(doc.text):
        prefix = f"{ref.accession_no}:{section.item}"
        for tc in chunk_section(section.text, id_prefix=prefix, spec=spec):
            out.append(
                Chunk(
                    id=tc.id,
                    filing_id=ref.accession_no,
                    accession_no=ref.accession_no,
                    form_type=ref.form_type,
                    ticker=ref.ticker,
                    fiscal_year=ref.fiscal_year,
                    fiscal_period=ref.fiscal_period,
                    item=section.item,
                    level="parent" if tc.level == "parent" else "child",
                    parent_id=tc.parent_id,
                    text=tc.text,
                    # Offsets become document-absolute so citations resolve to the filing.
                    char_start=section.char_start + tc.char_start,
                    char_end=section.char_start + tc.char_end,
                )
            )
    return out


def children(chunks: Iterable[Chunk]) -> list[Chunk]:
    return [c for c in chunks if c.level == "child"]
