# Development guide

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/) (backend)
- Node 22 (frontend)
- Docker (optional, for the full stack with Postgres/pgvector)

## Run it

**Fastest path — no Docker, no keys.** The backend defaults to an in-memory store and a deterministic hashing embedder, so ingestion and retrieval work offline. Research runs need `ANTHROPIC_API_KEY`.

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY (and VOYAGE_API_KEY for real embeddings)
make backend-install frontend-install
cd backend && uv run fin-research ingest AAPL --limit 4      # EDGAR → chunks (a minute or two)
uv run uvicorn fin_research.api.main:app_factory --factory --reload   # :8000
cd ../frontend && npm run dev                                # :5173, proxies /api → :8000
```

**Full stack:** `make up` — Postgres with pgvector (schema auto-applied), API with `STORE_BACKEND=postgres`, React UI on http://localhost:5173.

## Test and lint

```bash
make test     # pytest (backend) + vitest (frontend)
make lint     # ruff + mypy --strict (backend); oxlint + prettier + tsc (frontend)
```

Backend tests never call the network or an LLM: EDGAR/Voyage are mocked with `respx`, and the orchestrator runs against `FakeRuntime` with scripted agent outputs. Coverage is printed on every run.

## Conventions

- **Contracts first.** Anything crossing an agent boundary or the HTTP boundary is a Pydantic model in `backend/fin_research/schemas.py`, mirrored in `frontend/src/lib/types.ts`. Change both.
- **Numbers are code.** New metrics go in `backend/fin_research/tools/finance.py` as pure functions and are exposed through `QuantToolkit`, so they get provenance and `recompute` for free.
- **Prompts are files.** `backend/fin_research/agents/prompts/<agent>.md`; keep them stable — they're the cached prefix.
- **Tool docstrings are the schema.** The SDK builds tool descriptions and parameter docs from the Google-style docstring; `tests/test_agents.py` asserts every toolkit function has one.
- **One commit per feature**, message body explains the *why*.

## Adding a ticker's fundamentals

`QuantToolkit` takes a `load_fundamentals(ticker, fiscal_year)` callable. `fin_research/tools/market.py::fundamentals_from_companyfacts` maps an EDGAR companyfacts payload onto the statement keys `compute_ratios` expects; wire it in `api/deps.py` (currently a stub that raises until Phase 4 lands the `fundamentals` table loader).

## Where things are decided

Architecture decisions live in `docs/adr/`. Add a new ADR when you change something another engineer would ask "why?" about.
