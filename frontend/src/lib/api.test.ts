import { ApiError, api, subscribeToRun } from './api'
import type { RunEvent } from './types'

class FakeEventSource {
  listeners = new Map<string, (e: MessageEvent) => void>()
  closed = false
  onerror: (() => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners.set(type, fn)
  }
  emit(type: string, data: unknown) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(data) }))
  }
  close() {
    this.closed = true
  }
}

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('posts research requests and returns the run id', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ run_id: 'r1' }), { status: 202 }))
    const out = await api.startResearch('AAPL', 'q', 'deep')
    expect(out).toEqual({ run_id: 'r1' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/research')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ ticker: 'AAPL', question: 'q', depth: 'deep' })
  })

  it('surfaces FastAPI error details as ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'TSLA is not ingested; POST /ingest first' }), {
        status: 409,
      }),
    )
    await expect(api.startResearch('TSLA', 'q', 'brief')).rejects.toMatchObject({
      status: 409,
      message: 'TSLA is not ingested; POST /ingest first',
    })
    await expect(api.coverage()).rejects.toBeInstanceOf(ApiError)
  })

  it('subscribes to typed SSE events and closes on the close event', () => {
    let es!: FakeEventSource
    const received: RunEvent[] = []
    let closedWith: string | null = null
    const unsubscribe = subscribeToRun(
      'r1',
      (ev) => received.push(ev),
      (status) => {
        closedWith = status
      },
      (url) => {
        es = new FakeEventSource(url)
        return es as unknown as EventSource
      },
    )
    expect(es.url).toBe('/api/research/r1/events')
    const ev = { run_id: 'r1', agent: 'planner', type: 'plan', payload: {}, ts: 't' }
    es.emit('plan', ev)
    es.emit('ping', {})
    expect(received).toEqual([ev])
    es.emit('close', { status: 'done' })
    expect(closedWith).toBe('done')
    expect(es.closed).toBe(true)
    unsubscribe()
  })

  it('reports disconnects through onClose', () => {
    let es!: FakeEventSource
    let closedWith: string | null = null
    subscribeToRun(
      'r1',
      () => {},
      (s) => {
        closedWith = s
      },
      (url) => {
        es = new FakeEventSource(url)
        return es as unknown as EventSource
      },
    )
    es.onerror?.()
    expect(closedWith).toBe('disconnected')
  })
})

describe('api error fallback', () => {
  it('uses the HTTP status when the error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html>', { status: 502 }))
    await expect(api.coverage()).rejects.toMatchObject({ status: 502, message: 'HTTP 502' })
  })
})
