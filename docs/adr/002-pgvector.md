# ADR-002 — PostgreSQL + pgvector over a dedicated vector database

**Status:** Accepted · 2026-09-12

## Context
Corpus size for v1: ~20 tickers × ~12 filings × ~1 500 child chunks ≈ 360 k vectors at 1 024-d. Retrieval must combine dense similarity, BM25-style keyword search and hard metadata filters (ticker, fiscal year, item).

## Decision
Single PostgreSQL 16 with `pgvector` (HNSW index) and built-in `tsvector` full-text search. Fusion (RRF) done in SQL / Python.

## Consequences
+ One database for vectors, keyword index, metadata, fundamentals, run traces and eval sets — joins are trivial, filters are real `WHERE` clauses.
+ ACID ingestion (a filing is either fully indexed or absent).
+ Nothing extra to operate in compose.
− HNSW on pgvector is slower than Qdrant/Milvus at tens of millions of vectors — irrelevant at our scale, and the retriever sits behind an interface if that changes.

## Alternatives rejected
- Qdrant / Weaviate / Chroma — better pure-vector performance, but a second store with its own filter dialect and no joins to fundamentals.
- Elasticsearch / OpenSearch — strong hybrid search, heavier to run, redundant with Postgres for everything else.
