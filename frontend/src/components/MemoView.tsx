import type { ResearchResult } from '../lib/types'
import { isUnverified, splitRefs, stripUnverified, usd } from '../lib/format'

function Claim({ claim }: { claim: string }) {
  const flagged = isUnverified(claim)
  const { text, refs } = splitRefs(stripUnverified(claim))
  return (
    <li className={flagged ? 'unverified' : undefined}>
      {flagged && <strong>Unverified: </strong>}
      {text}
      {refs.map((r) => (
        <span key={r} className="ref" title={r.startsWith('F') ? 'Finding' : 'Metric'}>
          {r.length > 14 ? `${r.slice(0, 12)}…` : r}
        </span>
      ))}
    </li>
  )
}

export function MemoView({ result }: { result: ResearchResult }) {
  const { memo, verdict, cost } = result
  return (
    <article className="panel memo" aria-labelledby="memo-h">
      <header>
        <span className="label">
          {memo.ticker} · {result.depth} · {result.revisions} revision(s)
        </span>
        <h2 id="memo-h">{memo.title}</h2>
        <p className="thesis">{memo.thesis}</p>
      </header>

      {verdict && (
        <div className="verdict" role="status">
          <span className={`pill ${verdict.passed ? 'pass' : 'fail'}`}>
            {verdict.passed ? 'Critic: all claims supported' : 'Critic: unsupported claims flagged'}
          </span>
          <span className="muted">{verdict.claims.length} claims checked</span>
        </div>
      )}

      {memo.sections.map((s) => (
        <section key={s.heading}>
          <h3>{s.heading}</h3>
          <ul className="claims">
            {s.claims.map((c, i) => (
              <Claim key={i} claim={c} />
            ))}
          </ul>
        </section>
      ))}

      <div className="cases">
        <section>
          <h3>Bull case</h3>
          <ul>
            {memo.bull_case.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>Bear case</h3>
          <ul>
            {memo.bear_case.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </section>
      </div>

      <div className="stats" aria-label="Run cost">
        <div className="stat">
          <div className="v">{usd(cost.cost_usd)}</div>
          <div className="label">Cost</div>
        </div>
        <div className="stat">
          <div className="v">{cost.input_tokens.toLocaleString('en-US')}</div>
          <div className="label">Input tokens</div>
        </div>
        <div className="stat">
          <div className="v">{cost.output_tokens.toLocaleString('en-US')}</div>
          <div className="label">Output tokens</div>
        </div>
        <div className="stat">
          <div className="v">{cost.cache_read_tokens.toLocaleString('en-US')}</div>
          <div className="label">Cache reads</div>
        </div>
      </div>

      <p className="disclaimer">{memo.disclaimer}</p>
    </article>
  )
}
