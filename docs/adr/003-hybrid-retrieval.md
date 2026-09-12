# ADR-003 — Hybrid retrieval with reranking, not dense-only

**Status:** Accepted · 2026-09-12

## Context
Financial filings mix highly specific tokens (tickers, accounting standards like "ASC 842", product names, "Item 1A") with long paraphrased prose. Dense embeddings handle paraphrase well and exact rare tokens poorly; BM25 is the reverse.

## Decision
Run dense (`voyage-finance-2`, cosine, top-40) and sparse (`ts_rank`, top-40) in parallel with identical metadata filters, fuse with Reciprocal Rank Fusion, rerank the fused top-40 with a cross-encoder (`voyage rerank-2.5`) to the final top-8, then expand children to parents.

## Consequences
+ Measurable gain on the golden set for exact-term questions ("ASC 842 adoption impact") without hurting paraphrase questions.
+ Reranker cost is bounded: 40 pairs per query.
− Two indexes to keep consistent (both live in the same transaction, so this is cheap).
− Extra ~150 ms per query for the reranker.

## Alternatives rejected
- Dense-only — simpler; fails visibly on ticker / standard-number queries.
- Sparse-only — misses the "how did management describe demand softness" class of question.
