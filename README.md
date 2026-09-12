# Marginalia

**Multi-agent equity research grounded in SEC filings.**

Ask a question about a covered company — or ask for a full memo — and a team of Claude agents plans the research, retrieves the relevant passages from 10-Ks / 10-Qs / 8-Ks, runs the numbers through deterministic finance tools, writes a structured memo, and has an independent critic verify every claim against source before you see it.

Every qualitative statement is cited to a filing, section and character span. Every number links to the exact tool call that produced it.

## Documentation

- [System design](docs/SYSTEM_DESIGN.md) — architecture, agent roster, RAG pipeline, data model, evaluation, roadmap
- [Architecture decision records](docs/adr/) — why an orchestrator + sub-agents, why pgvector, why hybrid retrieval, why numbers never touch the LLM, why an independent critic

## Stack

Python 3.12 · Anthropic SDK (Claude Opus 5 / Sonnet 5 / Haiku 4.5) · Voyage AI embeddings · PostgreSQL 16 + pgvector · FastAPI · Streamlit · Docker Compose · OpenTelemetry

## Status

Design phase. See the roadmap in the system design document.

---
*Research support only — not investment advice.*
