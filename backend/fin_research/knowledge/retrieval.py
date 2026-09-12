"""Hybrid retriever: dense + sparse → RRF → (optional) rerank → expand to parents."""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

from fin_research.knowledge.embeddings import Embedder
from fin_research.knowledge.fusion import reciprocal_rank_fusion
from fin_research.knowledge.store import ChunkStore, Filters
from fin_research.schemas import Chunk, Citation, RetrievedChunk

Reranker = Callable[[str, list[Chunk]], list[float]]


@dataclass
class HybridRetriever:
    store: ChunkStore
    embedder: Embedder
    reranker: Reranker | None = None
    candidate_k: int = 40
    final_k: int = 8
    weights: tuple[float, float] = field(default=(1.0, 1.0))  # dense, sparse

    def search(self, query: str, filters: Filters | None = None) -> list[RetrievedChunk]:
        filters = filters or Filters()
        qvec = self.embedder.embed([query], input_type="query")[0]
        dense = [i for i, _ in self.store.dense_search(qvec, filters, self.candidate_k)]
        sparse = [i for i, _ in self.store.sparse_search(query, filters, self.candidate_k)]
        fused = reciprocal_rank_fusion([dense, sparse], weights=self.weights)[: self.candidate_k]

        children = [c for cid, _ in fused if (c := self.store.get(cid)) is not None]
        scores = dict(fused)
        if self.reranker and children:
            rr = self.reranker(query, children)
            order = sorted(range(len(children)), key=lambda i: -rr[i])
            children = [children[i] for i in order]
            scores = {children[j].id: rr[order[j]] for j in range(len(children))}

        # Dedupe by parent, expand child → parent so the model gets context.
        out: list[RetrievedChunk] = []
        seen_parents: set[str] = set()
        for child in children:
            key = child.parent_id or child.id
            if key in seen_parents:
                continue
            seen_parents.add(key)
            parent = self.store.get(child.parent_id) if child.parent_id else None
            out.append(
                RetrievedChunk(chunk=parent or child, score=scores[child.id], rank=len(out) + 1)
            )
            if len(out) >= self.final_k:
                break
        return out


def citation_for(chunk: Chunk, quote: str) -> Citation | None:
    """Locate `quote` inside `chunk` and return an absolute-offset citation, or None."""
    idx = chunk.text.find(quote)
    if idx < 0:
        return None
    return Citation(
        filing_id=chunk.filing_id,
        accession_no=chunk.accession_no,
        form_type=chunk.form_type,
        fiscal_year=chunk.fiscal_year,
        item=chunk.item,
        char_start=chunk.char_start + idx,
        char_end=chunk.char_start + idx + len(quote),
        quote=quote,
    )


@dataclass(frozen=True)
class SectionDiff:
    added: list[str]
    removed: list[str]
    unchanged: int


def compare_sections(
    store: ChunkStore, ticker: str, item: str, years: tuple[int, int]
) -> SectionDiff:
    """Paragraph-level diff of one Item across two fiscal years.

    "What changed in the risk factors" is the most common analyst question;
    it deserves a purpose-built path instead of two retrievals and a prayer.
    """

    def paragraphs(year: int) -> list[str]:
        text = "\n".join(c.text for c in store.list_sections(ticker, item, year))
        return [p.strip() for p in text.split("\n") if len(p.strip()) > 40]

    a, b = paragraphs(years[0]), paragraphs(years[1])
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    unchanged = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        else:
            removed.extend(a[i1:i2])
            added.extend(b[j1:j2])
    return SectionDiff(added=added, removed=removed, unchanged=unchanged)
