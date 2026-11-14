// Owner: Split A. Plain-text intake -> /extract, demo picker, follow-up questions.
// TODO(Split A): nicer form, answer follow-up questions inline (send answer text + current event to /extract).
import { useEffect, useState } from 'react'
import { api } from '../../api'

export default function IntakePanel({ event, setEvent, questions }) {
  const [text, setText] = useState('')
  const [demos, setDemos] = useState([])
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.demos().then(setDemos) }, [])

  const run = async () => {
    setBusy(true)
    try { const r = await api.extract(text, event); setEvent(r.event) } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <h2>1. Describe your event</h2>
      <textarea rows={5} value={text} onChange={e => setText(e.target.value)}
        placeholder="e.g. Diwali Night on Dec 12 in the TCC Ballroom, ~300 people, selling tickets, food from a local restaurant, DJ and dancing, asking USG for $3,500" />
      <div className="row">
        <button onClick={run} disabled={busy || !text}>{busy ? 'Reading…' : 'Plan my approvals'}</button>
        <span className="muted">or try a demo:</span>
        {demos.map(d => <button key={d.id} className="ghost" onClick={() => api.demo(d.id).then(setEvent)}>{d.name}</button>)}
      </div>
      {questions.length > 0 && (
        <div className="questions"><b>We still need:</b><ul>{questions.map(q => <li key={q}>{q}</li>)}</ul></div>
      )}
    </div>
  )
}
