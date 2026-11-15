// Owner: Split B. Mark each approval not started / submitted / approved / returned.
// Statuses live in event.tracking, so the engine re-checks with them automatically.
// "Blocking now" and the advisor email are built from the engine's result, nothing invented.
import { useState } from 'react'
import './tracker.css'

const STATUS = { not_started: 'Not started', submitted: 'Submitted', approved: 'Approved', returned: 'Returned' }
const DONE = new Set(['submitted', 'approved'])

const due = a => (a.days_left == null ? 'no fixed deadline'
  : a.days_left < 0 ? `deadline passed ${-a.days_left} day(s) ago`
  : a.days_left === 0 ? 'due today' : `due in ${a.days_left} day(s)`)

// What to do next, most urgent first: not done, and either flagged or waiting on something.
export function blocking(result) {
  const byId = Object.fromEntries(result.approvals.map(a => [a.id, a]))
  return result.approvals
    .filter(a => a.status !== 'approved' && (!DONE.has(a.status) || a.verdict !== 'ready'))
    .map(a => ({ ...a, waitingOn: a.depends_on.filter(d => byId[d]?.status !== 'approved').map(d => byId[d]?.name) }))
    .sort((x, y) => (x.days_left ?? 9999) - (y.days_left ?? 9999))
}

function advisorEmail(result, items) {
  const ev = result.event
  const lines = items.map(a => `- ${a.name} (${a.office}): ${STATUS[a.status] || a.status}, ${due(a)}${a.deadline ? ` [${a.deadline_label}]` : ''}`)
  return {
    subject: `${ev.name} (${ev.date || 'date TBD'}): approvals that need your sign-off`,
    body: `Hi,\n\nWe're planning ${ev.name} on ${ev.date || '(date TBD)'} at ${ev.venue?.name || '(venue TBD)'}. ` +
      `These approvals are still open:\n\n${lines.join('\n') || '- none'}\n\n` +
      `Could you review and sign off on the ones that need an advisor, especially anything due soon? ` +
      `Thank you!\n\n[Your name]\n[Club name]`,
  }
}

export default function Tracker({ result, event, setEvent }) {
  const [advisor, setAdvisor] = useState('')
  const [showEmail, setShowEmail] = useState(false)
  const [copied, setCopied] = useState(false)

  const setStatus = (id, status) =>
    setEvent({ ...event, tracking: { ...(event.tracking || {}), [id]: { status } } })

  const total = result.approvals.length
  const approved = result.approvals.filter(a => a.status === 'approved').length
  const items = blocking(result)
  const email = advisorEmail(result, items)
  const copy = () => navigator.clipboard?.writeText(`Subject: ${email.subject}\n\n${email.body}`)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }).catch(() => {})
  const mailto = `mailto:${encodeURIComponent(advisor)}?subject=${encodeURIComponent(email.subject)}&body=${encodeURIComponent(email.body)}`

  return (
    <div className="card tracker">
      <div className="tr-head">
        <h2>Tracker</h2>
        <span className="muted">{approved} of {total} approved</span>
      </div>
      <div className="tr-bar"><div style={{ width: total ? `${(100 * approved) / total}%` : 0 }} /></div>

      {items.length > 0 ? (
        <div className="tr-blocking">
          <b>Blocking now</b>
          <ol>
            {items.slice(0, 3).map(a => (
              <li key={a.id}>
                <span className={'tr-dot ' + a.color} /> {a.name} <span className="muted">· {due(a)}</span>
                {a.waitingOn.length > 0 && <span className="muted"> · waiting on {a.waitingOn.join(', ')}</span>}
              </li>
            ))}
          </ol>
          {items.length > 3 && <span className="muted">+{items.length - 3} more below</span>}
        </div>
      ) : <div className="tr-clear">✓ Nothing blocking. Every approval is approved or submitted cleanly.</div>}

      {result.approvals.map(a => (
        <div key={a.id} className={'tr-row s-' + a.status}>
          <span className={'tr-dot ' + a.color} />
          <span className="tr-name">
            {a.name}
            <span className="muted"> · {a.office} · {due(a)}</span>
          </span>
          <select value={a.status} onChange={e => setStatus(a.id, e.target.value)} aria-label={`Status of ${a.name}`}>
            {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      ))}

      <div className="tr-remind">
        <button className="ghost" onClick={() => setShowEmail(s => !s)} disabled={!items.length}>
          ✉ Remind advisor
        </button>
        {showEmail && (
          <div className="tr-email">
            <input value={advisor} onChange={e => setAdvisor(e.target.value)} placeholder="advisor@usc.edu" />
            <div className="muted small">Subject: {email.subject}</div>
            <pre>{email.body}</pre>
            <div className="row">
              <button onClick={copy}>{copied ? 'Copied ✓' : 'Copy email'}</button>
              <a className="btn-link" href={mailto}>Open in mail app</a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
