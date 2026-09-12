# FinResearchAgents

**Multi-agent equity research grounded in SEC filings.**

Ask a question about a covered company — or ask for a full memo — and a team of Claude agents plans the research, retrieves the relevant passages from 10-Ks / 10-Qs / 8-Ks through a hybrid-search RAG knowledge base, runs the numbers through deterministic finance tools, writes a structured memo, and has an independent critic verify every claim against source before you see it.

Every qualitative statement is cited to a filing, section and character span. Every number links to the exact tool call that produced it. Claims the critic cannot support are flagged, never silently dropped.

```
POST /research {ticker: "AAPL", depth: "deep"}
  planner (Opus 5) ─► ResearchPlan
  ├─ filings_analyst (Sonnet 5) ─ search_filings · read_section · compare_sections ─► Finding[] with citations
  └─ quant_analyst   (Sonnet 5) ─ get_fundamentals · compute_ratios · run_dcf · run_comps ─► MetricTable with provenance
  memo_writer (Opus 5, structured output) ─► Memo
  critic (Opus 5, fresh context) ─ search_filings · recompute ─► Verdict  ──┐
  revise ≤ 2× ◄─────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
cp .env.example .env               # set ANTHROPIC_API_KEY (VOYAGE_API_KEY optional)
make backend-install frontend-install
cd backend && uv run fin-research ingest AAPL --limit 4
uv run uvicorn fin_research.api.main:app_factory --factory --reload      # API on :8000
cd ../frontend && npm run dev                                           # UI on :5173
```

Or the whole stack with Postgres + pgvector: `make up`. Full instructions in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Codebase architecture

```
.
├── backend/                      Python 3.12 · FastAPI · Anthropic SDK          → backend/README.md
│   ├── fin_research/
│   │   ├── schemas.py            Typed contracts for every agent + API boundary (Finding, Memo, Verdict…)
│   │   ├── config.py             Settings from env / .env (models, keys, chunk sizes, budgets)
│   │   ├── ingestion/            EDGAR client → HTML clean → Item split → parent/child chunks
│   │   ├── knowledge/            Embedders (Voyage / hashing), chunk stores (memory / pgvector),
│   │   │                         RRF fusion, hybrid retriever, section diff, citation resolution
│   │   ├── tools/                Pure finance math (ratios, DCF, comps) + provenance registry
│   │   ├── agents/
│   │   │   ├── runtime.py        AgentSpec, AnthropicRuntime (SDK tool runner), FakeRuntime, pricing
│   │   │   ├── toolkits.py       Tool functions per agent, bound to store / registry
│   │   │   ├── roster.py         Which agent runs on which model, prompt, effort, output schema
│   │   │   ├── orchestrator.py   Plan → parallel fan-out → write → critic → revise loop → result
│   │   │   └── prompts/          One frozen system prompt per agent (the cached prefix)
│   │   ├── api/                  FastAPI app, dependency container, background run registry + SSE
│   │   └── cli.py                fin-research ingest | research | coverage
│   ├── sql/schema.sql            Postgres schema (pgvector HNSW + tsvector GIN)
│   ├── tests/                    pytest — 57 tests, no network, no tokens
│   └── Dockerfile
├── frontend/                     React 19 · TypeScript · Vite · Vitest            → frontend/README.md
│   ├── src/lib/                  types.ts (mirror of schemas.py), api.ts (fetch + SSE), format.ts
│   ├── src/hooks/useRun.ts       Follow a run's live event stream
│   ├── src/components/           ResearchForm · CoveragePanel · RunList · EventTrace · MemoView
│   ├── nginx.conf                Serves the bundle, proxies /api with SSE buffering off
│   └── Dockerfile
├── docs/                         → see below
├── docker-compose.yml            postgres (pgvector) · api · ui
├── Makefile                      install / test / lint for both halves
└── .github/workflows/ci.yml      ruff · mypy · pytest · oxlint · tsc · vitest · build
```

### Request flow

1. **UI / CLI** → `POST /research` — `api/main.py` validates, checks the ticker is ingested, creates a run and starts it on a background thread (`api/runs.py`).
2. **Orchestrator** (`agents/orchestrator.py`) asks the planner for a `ResearchPlan`, fans tasks out to the analysts in parallel, hands findings + metrics to the writer, then loops writer ↔ critic up to `depth`'s revision budget. Every step emits a `RunEvent`.
3. **Each agent** runs in its own SDK tool-runner (`agents/runtime.py`): frozen system prompt with a cache breakpoint, adaptive thinking, `output_format` set to its Pydantic contract, tools from `agents/toolkits.py`.
4. **Tools** reach data only through `knowledge/` (hybrid retrieval with citations) and `tools/` (pure math with provenance). Nothing in the agent layer touches Postgres or the network directly.
5. **Events** stream to the UI over SSE (`GET /research/{id}/events`); the final `ResearchResult` carries memo, verdict, cost ledger and the full trace.

## Documentation

| Read this | When you want to know |
|---|---|
| [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) | The whole design: goals, architecture, agent roster and protocol, RAG pipeline, data model, evaluation plan, security, roadmap |
| [docs/adr/](docs/adr/) | *Why* — orchestrator + sub-agents ([001](docs/adr/001-orchestrator-with-subagents.md)), pgvector ([002](docs/adr/002-pgvector.md)), hybrid retrieval ([003](docs/adr/003-hybrid-retrieval.md)), numbers via tools ([004](docs/adr/004-numbers-via-tools.md)), independent critic ([005](docs/adr/005-independent-critic.md)) |
| [docs/API.md](docs/API.md) | Every endpoint, the SSE event sequence, depth semantics, result shape |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Running locally or in Docker, testing, linting, project conventions |
| [backend/README.md](backend/README.md) · [frontend/README.md](frontend/README.md) | Per-package commands and layout |
| `backend/fin_research/schemas.py` | The source of truth for every data shape in the system |
| `backend/fin_research/agents/prompts/` | What each agent is told |

## Stack

Python 3.12 · Anthropic SDK (Claude Opus 5 / Sonnet 5 / Haiku 4.5) · Voyage AI `voyage-finance-2` · PostgreSQL 16 + pgvector · FastAPI · React 19 / Vite / TypeScript · Docker Compose · GitHub Actions

## Status

Phases 0–3 of the [roadmap](docs/SYSTEM_DESIGN.md#11-roadmap) are implemented: ingestion, knowledge base, finance tools, the five-agent team, API and console. Phase 4 (evaluation harness, golden set, Haiku metadata tagging, persisted runs) is next.

---
*Research support only — not investment advice.*
