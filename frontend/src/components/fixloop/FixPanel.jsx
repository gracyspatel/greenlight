// Owner: Split A. Edit the event and watch the verdict change live (the shell re-checks on every setEvent).
// Top: one-click fixes for the current flags (values found by asking the engine, see fixes.js).
// Below: every field the rules read, editable.
// Uses the `result` prop if App passes it; otherwise runs its own /check.
import { useEffect, useState } from 'react'
import { api } from '../../api'
import { allFixes, money, semesterOf } from './fixes'
import './fixloop.css'

const CATEGORIES = ['venue', 'food', 'entertainment', 'supplies', 'marketing', 'other']

export default function FixPanel({ event, setEvent, result: resultProp }) {
  const [own, setOwn] = useState(null)
  const [busy, setBusy] = useState('')
  const [notes, setNotes] = useState({})
  const result = resultProp || own

  useEffect(() => {
    if (resultProp || !event) return
    let live = true
    api.check(event).then(r => live && setOwn(r)).catch(() => {})
    return () => { live = false }
  }, [event, resultProp])

  const set = (path, value) => {
    const e = structuredClone(event)
    let o = e; const keys = path.split('.')
    keys.slice(0, -1).forEach(k => { o[k] = o[k] || {}; o = o[k] })
    o[keys.at(-1)] = value
    setEvent(e)
  }
  const lines = event.budget_lines || []
  const setLine = (i, k, v) => set('budget_lines', lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)))
  const addLine = () => set('budget_lines', [...lines, { item: '', category: 'other', amount: 0, quote_attached: false }])
  const dropLine = i => set('budget_lines', lines.filter((_, j) => j !== i))

  const fixes = result ? allFixes(result, event) : []
  const apply = async fx => {
    if (fx.focus) {
      const el = document.getElementById(fx.focus)
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' }); el?.focus()
      setNotes(n => ({ ...n, [fx.key]: fx.note }))
      return
    }
    setBusy(fx.key); setNotes(n => ({ ...n, [fx.key]: '' }))
    try {
      const next = await fx.run(event)
      if (next) setEvent(next)
      else setNotes(n => ({ ...n, [fx.key]: fx.fail || "Couldn't find a value that passes." }))
    } catch {
      setNotes(n => ({ ...n, [fx.key]: 'Something went wrong. Edit the fields below instead.' }))
    } finally { setBusy('') }
  }

  const venueTotal = lines.filter(l => l.category === 'venue').reduce((s, l) => s + (+l.amount || 0), 0)
  const linesTotal = lines.reduce((s, l) => s + (+l.amount || 0), 0)
  const funded = event.funding_source === 'USG' || event.funding_source === 'GSG'

  return (
    <div className="card fixpanel">
      <h2>2. Fix &amp; re-check</h2>

      {fixes.length > 0 && (
        <div className="fixes">
          <div className="fixes-head">Suggested fixes <span className="muted">· each value is checked by the rules before we use it</span></div>
          {fixes.map(fx => (
            <div key={fx.key} className={'fix ' + (fx.flags.some(x => x.flag.level === 'reject') ? 'reject' : 'risk')}>
              <div className="fix-what">
                {fx.flags.slice(0, 3).map(({ flag, approval }) => (
                  <div key={approval.id + flag.rule_id}><b>{approval.name}:</b> {flag.message}</div>
                ))}
                {fx.flags.length > 3 && <div className="muted">+ {fx.flags.length - 3} more</div>}
              </div>
              <button onClick={() => apply(fx)} disabled={!!busy}>{busy === fx.key ? 'Checking…' : fx.label}</button>
              {notes[fx.key] && <div className="fix-note">{notes[fx.key]}</div>}
            </div>
          ))}
        </div>
      )}
      {!resultProp && result && fixes.length === 0 && result.verdict === 'ready' && <p className="fix-clear">✓ Nothing to fix. Every rule we check passes.</p>}

      <fieldset>
        <legend>When &amp; where</legend>
        <div className="grid2">
          <label>Event date <input id="fix-date" type="date" value={event.date || ''} onChange={e => set('date', e.target.value)} /></label>
          <label>Expected people <input type="number" min="0" value={event.attendance || ''} onChange={e => set('attendance', +e.target.value)} /></label>
          <label className="span2">Venue <input value={event.venue?.name || ''} onChange={e => set('venue.name', e.target.value)} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={event.venue?.on_campus !== false} onChange={e => set('venue.on_campus', e.target.checked)} /> On campus</label>
        <label className="check"><input type="checkbox" checked={!!event.venue?.confirmed} onChange={e => set('venue.confirmed', e.target.checked)} /> Venue confirmed</label>
      </fieldset>

      <fieldset>
        <legend>What happens</legend>
        <label className="check"><input type="checkbox" checked={!!event.food?.served} onChange={e => set('food.served', e.target.checked)} /> Food or drinks</label>
        {event.food?.served && <>
          <label className="check indent"><input type="checkbox" checked={!!event.food?.sold} onChange={e => set('food.sold', e.target.checked)} /> Selling the food</label>
          <div className="grid2 indent">
            <label>Vendor <input value={event.food?.vendor || ''} onChange={e => set('food.vendor', e.target.value)} /></label>
            <label className="check"><input type="checkbox" checked={!!event.food?.vendor_approved} onChange={e => set('food.vendor_approved', e.target.checked)} /> USC-approved vendor</label>
          </div>
        </>}
        <label className="check"><input type="checkbox" checked={!!event.dancing} onChange={e => set('dancing', e.target.checked)} /> Dancing</label>
        <label className="check"><input type="checkbox" checked={!!event.ticket_sales} onChange={e => set('ticket_sales', e.target.checked)} /> Selling tickets</label>
      </fieldset>

      <fieldset>
        <legend>Money</legend>
        <div className="grid2">
          <label>Funding from
            <select value={event.funding_source || 'none'} onChange={e => set('funding_source', e.target.value)}>
              <option value="USG">USG</option><option value="GSG">GSG</option><option value="none">No funding request</option>
            </select>
          </label>
          {funded && <label>Amount requested ($) <input type="number" min="0" value={event.amount_requested || 0} onChange={e => set('amount_requested', +e.target.value)} /></label>}
        </div>
        {funded && <>
          <table className="lines">
            <thead><tr><th>Item</th><th>Category</th><th>$</th><th title="Vendor quote attached">Quote</th><th /></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td><input value={l.item} onChange={e => setLine(i, 'item', e.target.value)} /></td>
                  <td><select value={l.category} onChange={e => setLine(i, 'category', e.target.value)}>{CATEGORIES.map(c => <option key={c}>{c}</option>)}</select></td>
                  <td><input type="number" min="0" value={l.amount} onChange={e => setLine(i, 'amount', +e.target.value)} /></td>
                  <td className="c"><input type="checkbox" checked={!!l.quote_attached} onChange={e => setLine(i, 'quote_attached', e.target.checked)} /></td>
                  <td><button className="ghost x" onClick={() => dropLine(i)} aria-label="Remove line">×</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row between">
            <button className="ghost" onClick={addLine}>+ Add line</button>
            <span className="muted">Lines {money(linesTotal)} · venue {money(venueTotal)}</span>
          </div>
        </>}
      </fieldset>

      {funded && (
        <fieldset>
          <legend>Your club's funding so far</legend>
          <div className="grid2">
            <label>Events funded in {semesterOf(event.date)} <input id="fix-funded-events" type="number" min="0" value={event.org?.funded_events_this_semester ?? 0} onChange={e => set('org.funded_events_this_semester', +e.target.value)} /></label>
            <label>USG money received this year ($) <input type="number" min="0" value={event.org?.usg_received_this_year ?? 0} onChange={e => set('org.usg_received_this_year', +e.target.value)} /></label>
          </div>
        </fieldset>
      )}
    </div>
  )
}
