import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { DETAIL_DONE } from './test/fixtures'

function mockFetch(routes: Record<string, (init?: RequestInit) => unknown>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const key = `${init?.method ?? 'GET'} ${url.replace('/api', '')}`
    const handler = routes[key]
    if (!handler)
      return new Response(JSON.stringify({ detail: `no route ${key}` }), { status: 404 })
    return new Response(JSON.stringify(handler(init)), { status: 200 })
  })
}

describe('App', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads coverage and runs, then shows a finished run with its memo and trace', async () => {
    mockFetch({
      'GET /coverage': () => ({ AAPL: { chunks: 1200, latest_fiscal_year: 2024 } }),
      'GET /research': () => [{ ...DETAIL_DONE, result: undefined, events: undefined }],
      'GET /research/abc123': () => DETAIL_DONE,
    })
    render(<App />)
    expect(await screen.findByText('AAPL', { selector: 'span.mono' })).toBeInTheDocument()
    expect(screen.getByText(/1.2K chunks/)).toBeInTheDocument()
    expect(screen.getByText('Pick a run, or start a new one.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /AAPL.*done/ }))
    expect(
      await screen.findByRole('heading', { name: DETAIL_DONE.result!.memo.title }),
    ).toBeInTheDocument()
    expect(screen.getByText('filings_analyst: risk factors')).toBeInTheDocument()
  })

  it('starts research from the form and selects the new run', async () => {
    const runs: unknown[] = []
    mockFetch({
      'GET /coverage': () => ({ AAPL: { chunks: 10, latest_fiscal_year: 2024 } }),
      'GET /research': () => runs,
      'POST /research': () => {
        runs.push({ ...DETAIL_DONE, run_id: 'new1', result: undefined, events: undefined })
        return { run_id: 'new1' }
      },
      'GET /research/new1': () => ({ ...DETAIL_DONE, run_id: 'new1' }),
    })
    render(<App />)
    await screen.findByText('AAPL', { selector: 'span.mono' })
    await userEvent.click(screen.getByRole('button', { name: 'Run research' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /AAPL.*done/ })).toHaveAttribute(
        'aria-current',
        'true',
      ),
    )
    expect(
      await screen.findByRole('heading', { name: DETAIL_DONE.result!.memo.title }),
    ).toBeInTheDocument()
  })

  it('surfaces API failures as a notice', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => new Response(JSON.stringify({ detail: 'database down' }), { status: 500 }),
    )
    render(<App />)
    expect(await screen.findByRole('status')).toHaveTextContent('database down')
  })
})
