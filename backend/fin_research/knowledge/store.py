"""Chunk stores.

`ChunkStore` is the interface the retriever depends on. `InMemoryStore` backs
tests and small offline runs; `PostgresStore` is the production path on
pgvector + tsvector. Both expose the same two primitive searches (dense,
sparse) so fusion and reranking live in one place: the retriever.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from fin_research.knowledge.embeddings import cosine
from fin_research.schemas import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Filters:
    ticker: str | None = None
    fiscal_years: tuple[int, ...] = ()
    items: tuple[str, ...] = ()
    form_types: tuple[str, ...] = ()

    def matches(self, c: Chunk) -> bool:
        return (
            (self.ticker is None or c.ticker == self.ticker.upper())
            and (not self.fiscal_years or c.fiscal_year in self.fiscal_years)
            and (not self.items or c.item in self.items)
            and (not self.form_types or c.form_type in self.form_types)
        )


class ChunkStore(Protocol):
    def upsert(self, chunks: Iterable[Chunk], embeddings: dict[str, list[float]]) -> int: ...
    def get(self, chunk_id: str) -> Chunk | None: ...
    def dense_search(
        self, query_vec: list[float], filters: Filters, limit: int
    ) -> list[tuple[str, float]]: ...
    def sparse_search(
        self, query: str, filters: Filters, limit: int
    ) -> list[tuple[str, float]]: ...
    def list_sections(self, ticker: str, item: str, fiscal_year: int) -> list[Chunk]: ...
    def coverage(self) -> dict[str, dict[str, int]]: ...


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class InMemoryStore:
    """BM25 over children + brute-force cosine. Fine up to a few thousand chunks."""

    k1: float = 1.5
    b: float = 0.75
    _chunks: dict[str, Chunk] = field(default_factory=dict)
    _vecs: dict[str, list[float]] = field(default_factory=dict)
    _tf: dict[str, Counter[str]] = field(default_factory=dict)
    _df: Counter[str] = field(default_factory=Counter)

    def upsert(self, chunks: Iterable[Chunk], embeddings: dict[str, list[float]]) -> int:
        n = 0
        for c in chunks:
            if c.id in self._chunks:
                for tok in set(self._tf[c.id]):
                    self._df[tok] -= 1
            self._chunks[c.id] = c
            if c.id in embeddings:
                self._vecs[c.id] = embeddings[c.id]
            tf = Counter(_tokens(c.text))
            self._tf[c.id] = tf
            for tok in tf:
                self._df[tok] += 1
            n += 1
        return n

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def _candidates(self, filters: Filters) -> list[Chunk]:
        return [c for c in self._chunks.values() if c.level == "child" and filters.matches(c)]

    def dense_search(
        self, query_vec: list[float], filters: Filters, limit: int
    ) -> list[tuple[str, float]]:
        scored = [
            (c.id, cosine(query_vec, self._vecs[c.id]))
            for c in self._candidates(filters)
            if c.id in self._vecs
        ]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:limit]

    def sparse_search(self, query: str, filters: Filters, limit: int) -> list[tuple[str, float]]:
        cands = self._candidates(filters)
        if not cands:
            return []
        n_docs = len(self._tf)
        avgdl = sum(sum(tf.values()) for tf in self._tf.values()) / max(1, n_docs)
        q_tokens = _tokens(query)
        scored: list[tuple[str, float]] = []
        for c in cands:
            tf = self._tf[c.id]
            dl = sum(tf.values())
            score = 0.0
            for tok in q_tokens:
                if tok not in tf:
                    continue
                idf = math.log(1 + (n_docs - self._df[tok] + 0.5) / (self._df[tok] + 0.5))
                num = tf[tok] * (self.k1 + 1)
                den = tf[tok] + self.k1 * (1 - self.b + self.b * dl / avgdl)
                score += idf * num / den
            if score > 0:
                scored.append((c.id, score))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:limit]

    def list_sections(self, ticker: str, item: str, fiscal_year: int) -> list[Chunk]:
        return sorted(
            (
                c
                for c in self._chunks.values()
                if c.level == "parent"
                and c.ticker == ticker.upper()
                and c.item == item
                and c.fiscal_year == fiscal_year
            ),
            key=lambda c: c.char_start,
        )

    def coverage(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for c in self._chunks.values():
            t = out.setdefault(c.ticker, {"chunks": 0, "latest_fiscal_year": 0})
            t["chunks"] += 1
            t["latest_fiscal_year"] = max(t["latest_fiscal_year"], c.fiscal_year)
        return out


class PostgresStore:
    """pgvector + tsvector implementation. Requires `sql/schema.sql` applied."""

    def __init__(self, dsn: str) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self._conn = psycopg.connect(dsn, autocommit=True)
        register_vector(self._conn)

    @staticmethod
    def _where(filters: Filters, params: list[object]) -> str:
        clauses = ["level = 'child'"]
        if filters.ticker:
            clauses.append("ticker = %s")
            params.append(filters.ticker.upper())
        if filters.fiscal_years:
            clauses.append("fiscal_year = ANY(%s)")
            params.append(list(filters.fiscal_years))
        if filters.items:
            clauses.append("item = ANY(%s)")
            params.append(list(filters.items))
        if filters.form_types:
            clauses.append("form_type = ANY(%s)")
            params.append(list(filters.form_types))
        return " AND ".join(clauses)

    def upsert(self, chunks: Iterable[Chunk], embeddings: dict[str, list[float]]) -> int:
        rows = list(chunks)
        # Parents first so child parent_id FKs resolve.
        rows.sort(key=lambda c: 0 if c.level == "parent" else 1)
        with self._conn.cursor() as cur:
            for c in rows:
                cur.execute(
                    """
                    INSERT INTO chunks (id, filing_id, ticker, form_type, fiscal_year,
                        fiscal_period, item, level, parent_id, text, char_start, char_end,
                        tags, embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, tags = EXCLUDED.tags,
                        embedding = COALESCE(EXCLUDED.embedding, chunks.embedding)
                    """,
                    (
                        c.id,
                        c.filing_id,
                        c.ticker,
                        c.form_type,
                        c.fiscal_year,
                        c.fiscal_period,
                        c.item,
                        c.level,
                        c.parent_id,
                        c.text,
                        c.char_start,
                        c.char_end,
                        json.dumps(c.tags),
                        embeddings.get(c.id),
                    ),
                )
        return len(rows)

    def get(self, chunk_id: str) -> Chunk | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM chunks WHERE id = %s", (chunk_id,))
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description or []]
        return _row_to_chunk(dict(zip(cols, row, strict=True)))

    def dense_search(
        self, query_vec: list[float], filters: Filters, limit: int
    ) -> list[tuple[str, float]]:
        params: list[object] = []
        where = self._where(filters, params)
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT id, 1 - (embedding <=> %s::vector) AS score FROM chunks "
                f"WHERE {where} AND embedding IS NOT NULL "
                f"ORDER BY embedding <=> %s::vector LIMIT %s",
                [query_vec, *params, query_vec, limit],
            )
            return [(r[0], float(r[1])) for r in cur.fetchall()]

    def sparse_search(self, query: str, filters: Filters, limit: int) -> list[tuple[str, float]]:
        params: list[object] = []
        where = self._where(filters, params)
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT id, ts_rank_cd(tsv, q) AS score FROM chunks, "
                f"websearch_to_tsquery('english', %s) q WHERE {where} AND tsv @@ q "
                f"ORDER BY score DESC LIMIT %s",
                [query, *params, limit],
            )
            return [(r[0], float(r[1])) for r in cur.fetchall()]

    def list_sections(self, ticker: str, item: str, fiscal_year: int) -> list[Chunk]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM chunks WHERE level='parent' AND ticker=%s AND item=%s "
                "AND fiscal_year=%s ORDER BY char_start",
                (ticker.upper(), item, fiscal_year),
            )
            cols = [d.name for d in cur.description or []]
            return [_row_to_chunk(dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def coverage(self) -> dict[str, dict[str, int]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT ticker, count(*), max(fiscal_year) FROM chunks GROUP BY ticker")
            return {
                r[0]: {"chunks": int(r[1]), "latest_fiscal_year": int(r[2])} for r in cur.fetchall()
            }


def _row_to_chunk(row: dict[str, object]) -> Chunk:
    return Chunk(
        id=str(row["id"]),
        filing_id=str(row["filing_id"]),
        accession_no=str(row["filing_id"]),
        form_type=str(row["form_type"]),
        ticker=str(row["ticker"]),
        fiscal_year=int(str(row["fiscal_year"])),
        fiscal_period=str(row["fiscal_period"]),
        item=str(row["item"]),
        level="parent" if row["level"] == "parent" else "child",
        parent_id=str(row["parent_id"]) if row.get("parent_id") else None,
        text=str(row["text"]),
        char_start=int(str(row["char_start"])),
        char_end=int(str(row["char_end"])),
        tags=row["tags"] if isinstance(row["tags"], dict) else {},
    )
