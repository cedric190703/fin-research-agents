import { useCallback, useEffect, useState } from 'react'
import { CoveragePanel } from './components/CoveragePanel'
import { EventTrace } from './components/EventTrace'
import { MemoView } from './components/MemoView'
import { ResearchForm } from './components/ResearchForm'
import { RunList } from './components/RunList'
import { useRun } from './hooks/useRun'
import { api } from './lib/api'
import type { Coverage, Depth, RunSummary } from './lib/types'

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    try {
      const [cov, list] = await Promise.all([api.coverage(), api.listRuns()])
      setCoverage(cov)
      setRuns(list)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Refresh the run list (status pills) whenever the selected run finishes.
  const { detail, events } = useRun(selected, () => void refresh())

  const startResearch = async (ticker: string, question: string, depth: Depth) => {
    const { run_id } = await api.startResearch(ticker, question, depth)
    await refresh()
    setSelected(run_id)
  }

  const ingest = async (ticker: string) => {
    setIngesting(true)
    setNotice(null)
    try {
      const r = await api.ingest(ticker)
      setNotice(`Ingested ${r.filings} filings for ${r.ticker} (${r.chunks} chunks).`)
      await refresh()
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setIngesting(false)
    }
  }

  const tickers = coverage ? Object.keys(coverage).sort() : []

  return (
    <div className="app">
      <header className="masthead">
        <h1>FinResearchAgents</h1>
        <span className="tag">multi-agent equity research · SEC filings</span>
      </header>
      {notice && (
        <p className="muted" role="status">
          {notice}
        </p>
      )}
      <div className="layout">
        <aside style={{ display: 'grid', gap: 24 }}>
          <ResearchForm tickers={tickers} onSubmit={startResearch} />
          <CoveragePanel coverage={coverage} onIngest={ingest} busy={ingesting} />
          <RunList runs={runs} selected={selected} onSelect={setSelected} />
        </aside>
        <main className="main">
          {!selected && <p className="empty">Pick a run, or start a new one.</p>}
          {selected && detail?.result && <MemoView result={detail.result} />}
          {selected && detail?.status === 'error' && (
            <p className="error" role="alert">
              Run failed: {detail.error}
            </p>
          )}
          {selected && <EventTrace events={events} />}
        </main>
      </div>
    </div>
  )
}
