import type { RunSummary } from '../lib/types'

interface Props {
  runs: RunSummary[]
  selected: string | null
  onSelect: (id: string) => void
}

export function RunList({ runs, selected, onSelect }: Props) {
  return (
    <section className="panel runs" aria-labelledby="runs-h">
      <h2 id="runs-h">Runs</h2>
      {runs.length === 0 ? (
        <p className="muted">No runs yet.</p>
      ) : (
        <ul>
          {runs.map((r) => (
            <li key={r.run_id}>
              <button onClick={() => onSelect(r.run_id)} aria-current={r.run_id === selected}>
                <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <strong className="mono">{r.ticker}</strong>
                  <span className={`pill ${r.status}`}>{r.status}</span>
                </span>
                <span className="muted">{r.question}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
