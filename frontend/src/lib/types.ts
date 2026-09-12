// Mirrors backend/marginalia/schemas.py. Keep the two in sync by hand — the
// contract is small and a generated client would be heavier than it's worth.

export type Depth = 'brief' | 'standard' | 'deep'

export interface Citation {
  filing_id: string
  accession_no: string
  form_type: string
  fiscal_year: number
  item: string
  char_start: number
  char_end: number
  quote: string
}

export interface MemoSection {
  heading: string
  claims: string[]
}

export interface Memo {
  ticker: string
  title: string
  thesis: string
  sections: MemoSection[]
  bull_case: string[]
  bear_case: string[]
  disclaimer: string
}

export type ClaimStatus = 'supported' | 'unsupported' | 'needs_update'

export interface ClaimVerdict {
  claim: string
  status: ClaimStatus
  evidence: Citation[]
  note: string
}

export interface Verdict {
  passed: boolean
  claims: ClaimVerdict[]
}

export interface CostLedger {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cost_usd: number
}

export type EventType =
  | 'run_started'
  | 'plan'
  | 'agent_started'
  | 'tool_call'
  | 'finding'
  | 'metrics'
  | 'memo'
  | 'verdict'
  | 'done'
  | 'error'

export interface RunEvent {
  run_id: string
  agent: string
  type: EventType
  payload: Record<string, unknown>
  ts: string
}

export interface ResearchResult {
  run_id: string
  ticker: string
  question: string
  depth: Depth
  memo: Memo
  verdict: Verdict | null
  revisions: number
  cost: CostLedger
  events: RunEvent[]
}

export type RunStatus = 'queued' | 'running' | 'done' | 'error'

export interface RunSummary {
  run_id: string
  ticker: string
  question: string
  depth: Depth
  status: RunStatus
  started_at: string
  error: string | null
}

export interface RunDetail extends RunSummary {
  result: ResearchResult | null
  events: RunEvent[]
}

export type Coverage = Record<string, { chunks: number; latest_fiscal_year: number }>
