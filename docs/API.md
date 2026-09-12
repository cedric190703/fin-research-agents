# HTTP API

Base URL in development: `http://localhost:8000`. Behind the compose stack the frontend reaches it at `/api/*`. Interactive docs: `/docs` (Swagger UI) and `/redoc`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + wiring: which store, embedder, and whether an LLM runtime is configured |
| GET | `/coverage` | `{ TICKER: { chunks, latest_fiscal_year } }` for everything ingested |
| POST | `/ingest` | `{ ticker, limit? }` → fetch the latest filings from EDGAR, chunk, embed, index. Idempotent. |
| POST | `/research` | `{ ticker, question?, depth? }` → `202 { run_id }`. `409` if the ticker isn't ingested, `503` if no `ANTHROPIC_API_KEY`. |
| GET | `/research` | List runs, newest first |
| GET | `/research/{run_id}` | Status, events so far, and `result` once done |
| GET | `/research/{run_id}/events` | **Server-Sent Events** stream of `RunEvent`s |

## Event stream

Each SSE message has `event: <RunEvent.type>` and a JSON `data` body:

```json
{ "run_id": "3f9a…", "agent": "critic", "type": "verdict", "payload": { "verdict": { "passed": false, "claims": [] } }, "ts": "2026-09-12T14:02:11Z" }
```

Event types, in the order a `deep` run emits them:

`run_started` → `agent_started`(planner) → `plan` → `agent_started`(analysts, parallel) → `tool_call`* → `finding` / `metrics` → `agent_started`(memo_writer) → `memo` → `agent_started`(critic) → `tool_call`* → `verdict` → [re-check + `memo` + `verdict`]* → `done`

A failed run emits `error` with `payload.error` and a truncated traceback. The server sends `event: ping` every 15 s while idle and `event: close` with `{"status": "done"|"error"}` when the run ends. Late subscribers receive the full backlog first.

## Depth

| `depth` | Effort (planner / writer / critic) | Critic | Revisions |
|---|---|---|---|
| `brief` | low | no | 0 |
| `standard` | medium | yes | 1 |
| `deep` | high | yes | 2 |

## Result shape

`GET /research/{id}` → `result` is a `ResearchResult` (see `backend/marginalia/schemas.py` / `frontend/src/lib/types.ts`): `memo`, `verdict`, `revisions`, `cost` (tokens + USD), and the full `events` list. Claims the Critic could not support after the last revision are prefixed `⚠ UNVERIFIED:` — never removed.
