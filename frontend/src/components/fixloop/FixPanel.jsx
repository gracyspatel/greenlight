// Owner: Split A. Edit the event and watch the verdict change live (the shell re-checks on every setEvent).
// TODO(Split A): edit budget lines (amount, quote attached), "apply suggested fix" buttons, before/after diff.
export default function FixPanel({ event, setEvent }) {
  const set = (path, value) => {
    const e = structuredClone(event)
    let o = e; const keys = path.split('.')
    keys.slice(0, -1).forEach(k => { o[k] = o[k] || {}; o = o[k] })
    o[keys.at(-1)] = value
    setEvent(e)
  }
  return (
    <div className="card">
      <h2>2. Fix & re-check</h2>
      <label>Event date <input type="date" value={event.date || ''} onChange={e => set('date', e.target.value)} /></label>
      <label>Amount requested $ <input type="number" value={event.amount_requested || 0} onChange={e => set('amount_requested', +e.target.value)} /></label>
      <label><input type="checkbox" checked={!!event.venue?.confirmed} onChange={e => set('venue.confirmed', e.target.checked)} /> Venue confirmed</label>
      <label><input type="checkbox" checked={!!event.dancing} onChange={e => set('dancing', e.target.checked)} /> Dancing</label>
      <label><input type="checkbox" checked={!!event.ticket_sales} onChange={e => set('ticket_sales', e.target.checked)} /> Selling tickets</label>
      <label><input type="checkbox" checked={!!event.food?.sold} onChange={e => set('food.sold', e.target.checked)} /> Selling food</label>
    </div>
  )
}
