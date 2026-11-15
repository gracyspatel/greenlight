// Owner: Split B. Submission pack: drafted text per form, copy button, link to the system.
// Unlocks only when the engine's verdict is Ready.
import { useEffect, useState } from 'react'
import { api } from '../../api'
import './pack.css'

export default function PackView({ result, event, onSubmitted }) {
  const [drafts, setDrafts] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [sent, setSent] = useState(false)
  const ready = result.verdict === 'ready' && result.verdict_label === 'Ready'

  // any edit to the event makes old drafts stale
  useEffect(() => { setDrafts(null); setSent(false) }, [result])

  const build = async () => {
    setBusy(true); setError('')
    try { setDrafts(await api.pack(result)) } catch { setError("Couldn't build the pack just now. Try again.") }
    finally { setBusy(false) }
  }
  const copy = d => navigator.clipboard?.writeText(d.draft)
    .then(() => { setCopied(d.approval_id); setTimeout(() => setCopied(''), 1500) }).catch(() => {})
  const send = async () => {
    try { await api.submitToReviewer(event); setSent(true); onSubmitted?.() }
    catch { setError("Couldn't send to the reviewer queue.") }
  }

  if (!ready) {
    const n = (result.counts?.reject || 0) + (result.counts?.risk || 0)
    return (
      <div className="card pack locked">
        <h2>🔒 Submission pack</h2>
        <p className="muted">
          Unlocks when the verdict is <b>Ready</b>. {n > 0 ? `Fix the ${n} flagged approval(s) above first.` : 'Answer the open questions first.'}
        </p>
      </div>
    )
  }

  return (
    <div className="card pack">
      <div className="pk-head">
        <h2>Submission pack</h2>
        {!drafts && <button onClick={build} disabled={busy}>{busy ? 'Drafting…' : 'Build my submission pack'}</button>}
      </div>
      {error && <div className="error">{error}</div>}
      {!drafts && !busy && <p className="muted">Drafted text for every form, ready to paste. Fill in the [bracketed] parts.</p>}
      {drafts?.map(d => (
        <details key={d.approval_id} className="pk-item">
          <summary>
            <span className="pk-name">{d.name || d.approval_id}</span>
            <span className="muted"> · {d.system}{d.deadline_label ? ` · ${d.deadline_label}` : ''}</span>
            {d.by === 'ai' && <span className="pill pk-ai">AI-polished</span>}
          </summary>
          <pre className="pk-draft">{d.draft}</pre>
          <div className="row">
            <button onClick={() => copy(d)}>{copied === d.approval_id ? 'Copied ✓' : 'Copy'}</button>
            {d.link && <a className="btn-link" href={d.link} target="_blank" rel="noreferrer">Open {d.system} ↗</a>}
          </div>
        </details>
      ))}
      {drafts && (
        <div className="pk-send">
          <button onClick={send} disabled={sent}>{sent ? 'Sent ✓' : 'Send to USG reviewer queue →'}</button>
          <small className="muted">Drafts use only your event's facts. Check them before you submit.</small>
        </div>
      )}
    </div>
  )
}
