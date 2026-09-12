import { useState } from 'react'
import type { Depth } from '../lib/types'

interface Props {
  tickers: string[]
  onSubmit: (ticker: string, question: string, depth: Depth) => Promise<void>
  disabled?: boolean
}

const DEPTHS: { value: Depth; label: string; hint: string }[] = [
  { value: 'brief', label: 'Brief', hint: 'one analyst pass, no critic' },
  { value: 'standard', label: 'Standard', hint: 'critic, one revision' },
  { value: 'deep', label: 'Deep', hint: 'critic, two revisions' },
]

export function ResearchForm({ tickers, onSubmit, disabled }: Props) {
  const [ticker, setTicker] = useState(tickers[0] ?? '')
  const [question, setQuestion] = useState('Full research memo')
  const [depth, setDepth] = useState<Depth>('standard')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const current = tickers.includes(ticker) ? ticker : (tickers[0] ?? '')

  return (
    <form
      className="panel"
      aria-labelledby="research-h"
      onSubmit={async (e) => {
        e.preventDefault()
        setError(null)
        setBusy(true)
        try {
          await onSubmit(current, question.trim() || 'Full research memo', depth)
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2 id="research-h">New research</h2>
      <label className="field">
        <span className="label">Ticker</span>
        <select
          value={current}
          onChange={(e) => setTicker(e.target.value)}
          disabled={!tickers.length}
        >
          {tickers.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="label">Question</span>
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Full research memo, or a focused question"
        />
      </label>
      <label className="field">
        <span className="label">Depth</span>
        <select value={depth} onChange={(e) => setDepth(e.target.value as Depth)}>
          {DEPTHS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label} — {d.hint}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="btn" type="submit" disabled={disabled || busy || !current}>
        {busy ? 'Starting…' : 'Run research'}
      </button>
      {!tickers.length && <p className="muted">Ingest a ticker first.</p>}
    </form>
  )
}
