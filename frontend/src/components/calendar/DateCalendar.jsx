// Owner: Split B. Date picker that SUGGESTS, never decides.
// Each day is colored by the rules engine (/api/calendar): can every deadline still be met
// if the event is on that day? The user clicks a day, reads why, and chooses "Use this date".
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import './calendar.css'

const LEVEL = {
  ready: { icon: '✓', word: 'Works', long: 'Every deadline can still be met.' },
  risk: { icon: '!', word: 'Tight', long: 'Possible, but with warnings.' },
  reject: { icon: '✕', word: "Won't work", long: 'At least one deadline has already passed.' },
  past: { icon: '', word: 'Past', long: 'This day has already passed.' },
}
const WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

const iso = d => d.toISOString().slice(0, 10)
const parse = s => new Date(s + 'T00:00:00Z')
const addDays = (d, n) => new Date(d.getTime() + n * 86400000)
const monthStart = d => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1))
const fmt = (s, opts) => parse(s).toLocaleDateString('en-US', { timeZone: 'UTC', ...opts })
const long = s => fmt(s, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })

export default function DateCalendar({ event, setEvent }) {
  const today = event.as_of || iso(new Date())
  const [month, setMonth] = useState(() => monthStart(parse(event.date || today)))
  const [days, setDays] = useState(null)
  const [error, setError] = useState('')
  const [picked, setPicked] = useState(event.date || null)
  const [focus, setFocus] = useState(event.date || today)
  const gridRef = useRef(null)

  // the grid starts on the Sunday on/before the 1st: 6 weeks = 42 days
  const gridStart = useMemo(() => addDays(month, -month.getUTCDay()), [month])
  // re-rate when anything except the date changes (dates are what we're rating)
  const key = JSON.stringify({ ...event, date: null, text: null })

  useEffect(() => {
    let live = true
    setDays(null); setError('')
    api.calendar(event, iso(gridStart), 42)
      .then(d => live && setDays(d))
      .catch(() => live && setError("Couldn't load the calendar. Is the backend running?"))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, gridStart])

  useEffect(() => { setPicked(event.date || null) }, [event.date])

  const byDate = useMemo(() => Object.fromEntries((days || []).map(d => [d.date, d])), [days])
  const sel = picked && byDate[picked]
  const counts = (days || []).reduce((c, d) => {
    if (parse(d.date).getUTCMonth() === month.getUTCMonth()) c[d.level] = (c[d.level] || 0) + 1
    return c
  }, {})

  const goMonth = n => setMonth(m => new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + n, 1)))

  // arrow keys move between days (WAI-ARIA grid pattern)
  const onKey = e => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key]
    if (!step) return
    e.preventDefault()
    const next = iso(addDays(parse(focus), step))
    setFocus(next)
    const m = monthStart(parse(next))
    if (m.getTime() !== month.getTime()) setMonth(m)
    requestAnimationFrame(() => gridRef.current?.querySelector(`[data-date="${next}"]`)?.focus())
  }

  return (
    <div className="card cal">
      <h3 className="cal-title">Choose your event date</h3>
      <p className="muted cal-help">
        Colors show whether every approval deadline can still be met for that day.
        Pick a day to see why. Nothing changes until you choose “Use this date”.
      </p>

      <div className="cal-legend" aria-hidden="true">
        {['ready', 'risk', 'reject'].map(k => (
          <span key={k} className={'cal-key ' + k}><span className="cal-swatch">{LEVEL[k].icon}</span>{LEVEL[k].word}</span>
        ))}
      </div>

      <div className="cal-nav">
        <button className="ghost" onClick={() => goMonth(-1)} aria-label="Previous month">‹</button>
        <h4 aria-live="polite">{month.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'long', year: 'numeric' })}</h4>
        <button className="ghost" onClick={() => goMonth(1)} aria-label="Next month">›</button>
      </div>
      {days && (
        <p className="cal-summary muted" aria-live="polite">
          This month: {counts.ready || 0} day(s) work, {counts.risk || 0} tight, {counts.reject || 0} won't work.
        </p>
      )}

      {error && <div className="error">{error}</div>}
      <table className="cal-grid" role="grid" aria-label="Event date options" ref={gridRef} onKeyDown={onKey} aria-busy={!days}>
        <thead><tr>{WEEK.map(w => <th key={w} scope="col" abbr={w}>{w[0]}<span className="cal-wk">{w.slice(1)}</span></th>)}</tr></thead>
        <tbody>
          {[0, 1, 2, 3, 4, 5].map(w => (
            <tr key={w}>
              {[0, 1, 2, 3, 4, 5, 6].map(i => {
                const date = iso(addDays(gridStart, w * 7 + i))
                const d = byDate[date]
                const level = d?.level || 'loading'
                const outside = parse(date).getUTCMonth() !== month.getUTCMonth()
                const isEvent = date === event.date
                const label = `${long(date)}. ${d ? LEVEL[d.level].word + '. ' + LEVEL[d.level].long : 'Loading.'}${isEvent ? ' Your current date.' : ''}`
                return (
                  <td key={i} role="gridcell" aria-selected={picked === date}>
                    <button
                      data-date={date}
                      className={`cal-day ${level}${outside ? ' outside' : ''}${picked === date ? ' picked' : ''}${isEvent ? ' current' : ''}`}
                      tabIndex={date === focus ? 0 : -1}
                      aria-disabled={!d || level === 'past'}
                      aria-label={label}
                      onClick={() => { setFocus(date); if (d && level !== 'past') setPicked(date) }}
                    >
                      <span className="cal-num">{parse(date).getUTCDate()}</span>
                      {d && level !== 'past' && <span className="cal-icon" aria-hidden="true">{LEVEL[level].icon}</span>}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="cal-detail" aria-live="polite">
        {!sel ? <p className="muted">Pick a day to see if it works.</p> : (
          <div className={'cal-pick ' + sel.level}>
            <div className="cal-pick-head">
              <span className="cal-swatch big" aria-hidden="true">{LEVEL[sel.level].icon}</span>
              <div>
                <b>{long(sel.date)}</b>
                <div>{LEVEL[sel.level].word}: {LEVEL[sel.level].long}</div>
              </div>
            </div>
            {sel.reasons.length > 0 && <ul>{sel.reasons.map(r => <li key={r}>{r}</li>)}</ul>}
            {sel.notes?.length > 0 && (
              <div className="cal-notes">
                <b>Warning (can't be changed, just good to know):</b>
                <ul>{sel.notes.map(n => <li key={n}>{n}</li>)}</ul>
              </div>
            )}
            {sel.date === event.date
              ? <p className="muted">This is your event's current date.</p>
              : (
                <div className="row">
                  <button onClick={() => setEvent({ ...event, date: sel.date })}>Use this date</button>
                  {sel.level === 'reject' && <span className="muted">You can still choose it, but it will be flagged.</span>}
                </div>
              )}
          </div>
        )}
        <p className="muted small">Only deadlines are shown here. Other problems (like budget) are listed below.</p>
      </div>
    </div>
  )
}
