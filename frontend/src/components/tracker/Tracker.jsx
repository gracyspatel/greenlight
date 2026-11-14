// Owner: Split B. Mark each approval submitted / approved / returned.
// Statuses live in event.tracking, so the engine re-checks with them automatically.
// TODO(Split B): advisor reminder button, "what's blocking" summary.
export default function Tracker({ result, event, setEvent }) {
  const setStatus = (id, status) =>
    setEvent({ ...event, tracking: { ...(event.tracking || {}), [id]: { status } } })
  return (
    <div className="card">
      <h2>Tracker</h2>
      {result.approvals.map(a => (
        <div key={a.id} className="row">
          <span style={{ flex: 1 }}>{a.name}</span>
          <select value={a.status} onChange={e => setStatus(a.id, e.target.value)}>
            {['not_started', 'submitted', 'approved', 'returned'].map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
      ))}
    </div>
  )
}
