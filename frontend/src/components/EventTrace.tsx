import type { RunEvent } from '../lib/types'

function describe(ev: RunEvent): string {
  const p = ev.payload
  switch (ev.type) {
    case 'run_started':
      return `${String(p.ticker)} · ${String(p.depth)} · “${String(p.question)}”`
    case 'plan': {
      const plan = p.plan as { tasks?: { agent: string; task: string }[] } | undefined
      return (plan?.tasks ?? []).map((t) => `${t.agent}: ${t.task}`).join(' · ')
    }
    case 'agent_started':
      return p.task ? String(p.task) : 'started'
    case 'tool_call':
      return `${String(p.tool)}(${JSON.stringify(p.args ?? {})})`
    case 'finding':
      return `${String(p.count)} finding(s)`
    case 'metrics':
      return `${String(p.count)} metric(s)`
    case 'memo':
      return 'draft memo produced'
    case 'verdict': {
      const v = p.verdict as { passed?: boolean; claims?: { status: string }[] } | undefined
      const bad = (v?.claims ?? []).filter((c) => c.status !== 'supported').length
      return v?.passed ? 'passed' : `${bad} claim(s) not supported`
    }
    case 'done':
      return `finished after ${String(p.revisions)} revision(s)`
    case 'error':
      return String(p.error)
    default:
      return ''
  }
}

export function EventTrace({ events }: { events: RunEvent[] }) {
  return (
    <section className="panel trace" aria-labelledby="trace-h">
      <h2 id="trace-h">Trace</h2>
      {events.length === 0 ? (
        <p className="muted">Waiting for the first event…</p>
      ) : (
        <ul>
          {events.map((ev, i) => (
            <li key={`${ev.ts}-${i}`}>
              <span className="agent">{ev.agent}</span>
              <span className={`type ${ev.type}`}>{ev.type.replace('_', ' ')}</span>
              <span className="detail">{describe(ev)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
