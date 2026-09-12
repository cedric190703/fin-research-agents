import type { ResearchResult, RunDetail, RunEvent } from '../lib/types'

export const RESULT: ResearchResult = {
  run_id: 'abc123',
  ticker: 'AAPL',
  question: 'Full research memo',
  depth: 'deep',
  memo: {
    ticker: 'AAPL',
    title: 'Apple: services carry the margin story',
    thesis: 'Hardware is mature; services mix keeps gross margin expanding.',
    sections: [
      {
        heading: 'Risks',
        claims: [
          'Supplier concentration in Taiwan remains the key operational risk. [F1]',
          '⚠ UNVERIFIED: Management expects tariffs to be immaterial. [F2]',
          'Gross margin reached 45% in FY2024. [Mcompute_ratios.gross_margin.9f8e7d6c5b4a3210]',
        ],
      },
    ],
    bull_case: ['Services growth'],
    bear_case: ['China exposure'],
    disclaimer: 'Research support only. Not investment advice.',
  },
  verdict: {
    passed: false,
    claims: [
      { claim: 'a', status: 'supported', evidence: [], note: '' },
      { claim: 'b', status: 'unsupported', evidence: [], note: 'no source' },
    ],
  },
  revisions: 2,
  cost: { input_tokens: 12000, output_tokens: 3000, cache_read_tokens: 8000, cost_usd: 0.4321 },
  events: [],
}

export const EVENTS: RunEvent[] = [
  {
    run_id: 'abc123',
    agent: 'orchestrator',
    type: 'run_started',
    payload: { ticker: 'AAPL', depth: 'deep', question: 'q' },
    ts: '2026-09-12T10:00:00Z',
  },
  {
    run_id: 'abc123',
    agent: 'planner',
    type: 'plan',
    payload: { plan: { tasks: [{ agent: 'filings_analyst', task: 'risk factors' }] } },
    ts: '2026-09-12T10:00:01Z',
  },
  {
    run_id: 'abc123',
    agent: 'filings_analyst',
    type: 'tool_call',
    payload: { tool: 'search_filings', args: { query: 'Taiwan' } },
    ts: '2026-09-12T10:00:02Z',
  },
  {
    run_id: 'abc123',
    agent: 'critic',
    type: 'verdict',
    payload: {
      verdict: { passed: false, claims: [{ status: 'unsupported' }, { status: 'supported' }] },
    },
    ts: '2026-09-12T10:00:03Z',
  },
  {
    run_id: 'abc123',
    agent: 'orchestrator',
    type: 'error',
    payload: { error: 'RuntimeError: boom' },
    ts: '2026-09-12T10:00:04Z',
  },
]

export const DETAIL_DONE: RunDetail = {
  run_id: 'abc123',
  ticker: 'AAPL',
  question: 'Full research memo',
  depth: 'deep',
  status: 'done',
  started_at: '2026-09-12T10:00:00Z',
  error: null,
  result: RESULT,
  events: EVENTS.slice(0, 2),
}
