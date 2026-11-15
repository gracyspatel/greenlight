// Owner: Split A. Plain-text intake -> /extract, demo picker, follow-up questions answered inline.
// A new description always starts a fresh event; a follow-up answer is merged into the current one
// (sent as "Q: <question>\nA: <answer>" together with the current event).
import { useEffect, useState } from 'react'
import { api } from '../../api'
import './intake.css'

const money = n => '$' + Math.round(n || 0).toLocaleString()
const pretty = d => (d ? new Date(d + 'T00:00:00Z').toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) : null)

export default function IntakePanel({ event, setEvent, questions }) {
  const [text, setText] = useState('')
  const [demos, setDemos] = useState([])
  const [asOf, setAsOf] = useState(null) // demo texts are checked "as of" the demo's date
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api.demos().then(setDemos).catch(() => {}) }, [])

  const run = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.extract(text, asOf ? { as_of: asOf } : null)
      setEvent(r.event)
    } catch {
      setError("Couldn't read that just now. Try again, or pick a demo.")
    } finally { setBusy(false) }
  }

  const loadDemo = async id => {
    setError('')
    try {
      const d = await api.demo(id)
      const { text: demoText, ...ev } = d
      setText(demoText || '')
      setAsOf(d.as_of || null)
      setEvent(ev)
    } catch { setError("Couldn't load that demo.") }
  }

  return (
    <div className="card intake">
      <h2>1. Describe your event</h2>
      <textarea rows={5} value={text}
        onChange={e => { setText(e.target.value); if (!e.target.value) setAsOf(null) }}
        onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && text && !busy) run() }}
        placeholder="e.g. Diwali Night on Dec 12 in the TCC Ballroom, ~300 people, selling tickets, food from a local restaurant, DJ and dancing, asking USG for $3,500" />
      <div className="row">
        <button onClick={run} disabled={busy || !text.trim()}>{busy ? 'Reading…' : 'Plan my approvals'}</button>
        {demos.length > 0 && <span className="muted">or try a demo:</span>}
        {demos.map(d => <button key={d.id} className="ghost" onClick={() => loadDemo(d.id)}>{d.name}</button>)}
      </div>
      {error && <div className="intake-error">{error}</div>}

      {event && <Understood event={event} />}

      {event && questions.length > 0 && (
        <div className="questions">
          <b>A few things we still need</b>
          {questions.map(q => <Question key={q} q={q} event={event} setEvent={setEvent} />)}
        </div>
      )}
    </div>
  )
}

function Understood({ event: e }) {
  const items = [
    ['Date', pretty(e.date)],
    ['Venue', e.venue?.name ? `${e.venue.name}${e.venue.on_campus === false ? ' (off campus)' : ''}${e.venue.confirmed ? ' ✓ booked' : ''}` : null],
    ['People', e.attendance || null],
    ['Funding', e.funding_source && e.funding_source !== 'none' ? `${e.funding_source} · ${money(e.amount_requested)}` : 'No request'],
    ['Food', e.food?.served ? (e.food.sold ? 'Sold' : 'Free') + (e.food.vendor ? ` · ${e.food.vendor}` : '') : 'None'],
    ['Tickets', e.ticket_sales ? 'Yes' : 'No'],
    ['Dancing', e.dancing ? 'Yes' : 'No'],
  ]
  return (
    <div className="understood">
      <div className="muted small">Here's what we understood. Fix anything wrong in step 3.</div>
      <div className="facts">
        {items.map(([k, v]) => (
          <span key={k} className={'fact' + (v ? '' : ' missing')}><span className="k">{k}</span> {v ?? 'missing'}</span>
        ))}
      </div>
    </div>
  )
}

function Question({ q, event, setEvent }) {
  const [a, setA] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const send = async () => {
    if (!a.trim()) return
    setBusy(true); setErr('')
    try {
      const r = await api.extract(`Q: ${q}\nA: ${a.trim()}`, event)
      setEvent(r.event)
      setA('')
    } catch {
      setErr("Couldn't add that. Try again, or set it in step 3.")
    } finally { setBusy(false) }
  }
  return (
    <div className="q">
      <label>{q}</label>
      <div className="q-row">
        <input value={a} onChange={e => setA(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} disabled={busy} placeholder="Type your answer" />
        <button onClick={send} disabled={busy || !a.trim()}>{busy ? 'Adding…' : 'Add'}</button>
      </div>
      {err && <div className="intake-error">{err}</div>}
    </div>
  )
}
