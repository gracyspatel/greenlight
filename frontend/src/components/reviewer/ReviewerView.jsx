// Owner: Split B. USG reviewer queue of pre-checked applications, filter by verdict.
// The verdict comes from the rules engine; the summary is AI-written (or rule text if no key).
import { useEffect, useState } from 'react'
import { api } from '../../api'
import './reviewer.css'

const FILTERS = [['all', 'All'], ['reject', 'Will be rejected'], ['risk', 'At risk'], ['ready', 'Ready']]
const money = n => '$' + Math.round(n || 0).toLocaleString()

export default function ReviewerView() {
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState('')

  const load = () => {
    setRows(null); setError('')
    api.reviewerQueue().then(setRows).catch(() => { setRows([]); setError("Couldn't load the queue.") })
  }
  useEffect(load, [])

  const count = k => (rows || []).filter(r => k === 'all' || r.verdict === k).length
  const shown = (rows || []).filter(r => filter === 'all' || r.verdict === filter)

  return (
    <div className="card reviewer">
      <div className="rv-head">
        <h2>USG review queue</h2>
        <button className="ghost" onClick={load}>↻ Refresh</button>
      </div>
      <div className="rv-filters">
        {FILTERS.map(([k, label]) => (
          <button key={k} className={filter === k ? 'on' : 'ghost'} onClick={() => setFilter(k)}>
            {label} <b>{rows ? count(k) : ''}</b>
          </button>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      {!rows && <p className="muted">Checking every application against the rules…</p>}
      {rows && !shown.length && <p className="muted">Nothing here.</p>}
      {shown.length > 0 && (
        <table>
          <thead><tr><th>Event</th><th>Date</th><th>Requested</th><th>Rule check</th><th>Summary</th></tr></thead>
          <tbody>{shown.map(r => (
            <tr key={r.id}>
              <td>
                <b>{r.name}</b>
                {r.source === 'submitted' && <span className="pill rv-new">New</span>}
                {r.venue && <div className="muted">{r.venue}{r.attendance ? ` · ${r.attendance} people` : ''}</div>}
              </td>
              <td>{r.date || '—'}</td>
              <td>{money(r.requested)}</td>
              <td><span className={'pill ' + r.verdict}>{r.verdict_label}</span></td>
              <td className="rv-summary">{r.summary}{r.by === 'ai' && <span className="muted"> · AI summary</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <small className="muted">Rule checks are automatic and quote USC's written rules. USG makes every final decision.</small>
    </div>
  )
}
