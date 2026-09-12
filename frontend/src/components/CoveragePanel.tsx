import type { Coverage } from '../lib/types'
import { compact } from '../lib/format'

interface Props {
  coverage: Coverage | null
  onIngest: (ticker: string) => Promise<void>
  busy: boolean
}

export function CoveragePanel({ coverage, onIngest, busy }: Props) {
  const tickers = coverage ? Object.keys(coverage).sort() : []
  return (
    <section className="panel coverage" aria-labelledby="coverage-h">
      <h2 id="coverage-h">Knowledge base</h2>
      {tickers.length === 0 ? (
        <p className="muted">Nothing ingested yet. Add a ticker to fetch its filings from EDGAR.</p>
      ) : (
        <ul>
          {tickers.map((t) => (
            <li key={t}>
              <span className="mono">{t}</span>
              <span className="muted">
                {compact(coverage![t].chunks)} chunks · through FY{coverage![t].latest_fiscal_year}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const form = e.currentTarget
          const input = form.elements.namedItem('ingest') as HTMLInputElement
          const t = input.value.trim().toUpperCase()
          if (!t) return
          void onIngest(t).then(() => {
            input.value = ''
          })
        }}
        style={{ display: 'flex', gap: 8 }}
      >
        <input
          name="ingest"
          aria-label="Ticker to ingest"
          placeholder="e.g. MSFT"
          maxLength={10}
          style={{
            flex: 1,
            border: '1px solid var(--rule)',
            padding: '6px 8px',
            background: 'var(--bg)',
          }}
        />
        <button className="btn secondary" type="submit" disabled={busy}>
          {busy ? 'Ingesting…' : 'Ingest'}
        </button>
      </form>
    </section>
  )
}
