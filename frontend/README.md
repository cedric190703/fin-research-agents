# FinResearchAgents frontend

React 19 · TypeScript · Vite · Vitest · oxlint + Prettier. See the [root README](../README.md) for the codebase map.

```bash
npm ci            # install
npm run dev       # dev server on :5173, proxies /api → http://localhost:8000
npm test          # vitest (watch); `npm test -- --run` for one pass
npm run lint      # oxlint + prettier --check
npm run typecheck # tsc -b --noEmit
npm run build     # production bundle in dist/
```

## Layout

| Path                  | What                                                                      |
| --------------------- | ------------------------------------------------------------------------- |
| `src/lib/types.ts`    | TypeScript mirror of `backend/fin_research/schemas.py` — the API contract |
| `src/lib/api.ts`      | fetch client + `subscribeToRun` (SSE)                                     |
| `src/hooks/useRun.ts` | Loads a run and follows its live event stream until it closes             |
| `src/components/`     | `ResearchForm`, `CoveragePanel`, `RunList`, `EventTrace`, `MemoView`      |
| `src/App.tsx`         | Composition: sidebar (form, knowledge base, runs) + main (memo, trace)    |
| `src/test/`           | Vitest setup and shared fixtures                                          |

Tests live next to the code they test (`*.test.ts(x)`). The `react/set-state-in-effect` lint rule is disabled in `.oxlintrc.json`: it flags `await`-then-`setState` data loading, which is the intended pattern here.
