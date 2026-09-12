import type { Coverage, Depth, RunDetail, RunEvent, RunSummary } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  coverage: () => request<Coverage>('/coverage'),
  listRuns: () => request<RunSummary[]>('/research'),
  getRun: (id: string) => request<RunDetail>(`/research/${id}`),
  startResearch: (ticker: string, question: string, depth: Depth) =>
    request<{ run_id: string }>('/research', {
      method: 'POST',
      body: JSON.stringify({ ticker, question, depth }),
    }),
  ingest: (ticker: string) =>
    request<{ ticker: string; filings: number; chunks: number }>('/ingest', {
      method: 'POST',
      body: JSON.stringify({ ticker }),
    }),
}

export { ApiError }

/**
 * Subscribe to a run's live event stream. Calls `onEvent` for each RunEvent and
 * `onClose` when the server closes the stream. Returns an unsubscribe function.
 */
export function subscribeToRun(
  runId: string,
  onEvent: (ev: RunEvent) => void,
  onClose: (status: string) => void,
  factory: (url: string) => EventSource = (url) => new EventSource(url),
): () => void {
  const es = factory(`${API_BASE}/research/${runId}/events`)
  const types: string[] = [
    'run_started',
    'plan',
    'agent_started',
    'tool_call',
    'finding',
    'metrics',
    'memo',
    'verdict',
    'done',
    'error',
  ]
  for (const t of types) {
    es.addEventListener(t, (e) => onEvent(JSON.parse((e as MessageEvent).data) as RunEvent))
  }
  es.addEventListener('close', (e) => {
    const { status } = JSON.parse((e as MessageEvent).data) as { status: string }
    es.close()
    onClose(status)
  })
  es.onerror = () => {
    es.close()
    onClose('disconnected')
  }
  return () => es.close()
}
