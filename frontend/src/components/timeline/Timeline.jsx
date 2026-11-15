// Owner: Split A. Backward timeline: every approval's deadline on one axis from today to the event.
// Colors come from approval.color (engine): red = past due, yellow = due within 7 days, green, done, none.
import './timeline.css'

const DAY = 86400000
const t = s => new Date(s + 'T00:00:00Z').getTime()
const short = s => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' })
const STATUS = { red: 'Past due', yellow: 'Due soon', green: 'On track', done: 'Done', none: 'No fixed deadline' }

export default function Timeline({ result }) {
  const today = result.as_of
  const eventDate = result.event?.date
  const dated = result.approvals.filter(a => a.deadline)
  const undated = result.approvals.filter(a => !a.deadline)
  // the engine's step numbers, so #N matches the cards and the Tracker (undated steps keep theirs)
  const num = Object.fromEntries(result.approvals.map(a => [a.id, a.order]))
  const after = a => a.depends_on.map(d => (num[d] ? `#${num[d]} ${nameOf[d]}` : nameOf[d] || d)).join(', ')
  const nameOf = Object.fromEntries(result.approvals.map(a => [a.id, a.name]))

  if (!eventDate) {
    return (
      <div className="card"><h2>Approval timeline</h2>
        <p className="muted">Add the event date and we'll count every deadline back from it.</p></div>
    )
  }

  const start = Math.min(t(today), ...dated.map(a => t(a.deadline)))
  const end = Math.max(t(eventDate), t(today) + DAY)
  const span = Math.max(end - start, DAY)
  const pos = d => `${((t(d) - start) / span) * 100}%`
  const daysToEvent = Math.round((t(eventDate) - t(today)) / DAY)
  const overdue = dated.filter(a => a.color === 'red').length

  return (
    <div className="card timeline-card">
      <div className="tl-head">
        <h2>Approval timeline</h2>
        <span className="muted">
          {daysToEvent >= 0 ? `${daysToEvent} days to the event` : 'Event date has passed'} · checked as of {short(today)}
          {overdue > 0 && <b className="tl-overdue"> · {overdue} past due</b>}
        </span>
      </div>

      <div className="tl">
        <div className="tl-axis">
          <span className="tl-axis-label" style={{ left: pos(today) }}>Today</span>
          <span className="tl-axis-label end" style={{ left: pos(eventDate) }}>Event · {short(eventDate)}</span>
        </div>
        <div className="tl-rows">
          <div className="tl-overlay">
            <div className="tl-today" style={{ left: pos(today) }} />
            <div className="tl-event" style={{ left: pos(eventDate) }} />
          </div>
          {dated.map(a => {
            const late = t(a.deadline) < t(today)
            const [l, r] = late ? [a.deadline, today] : [today, a.deadline]
            return (
              <div key={a.id} className={'tl-row c-' + a.color}>
                <div className="tl-label">
                  <span className="tl-num">{num[a.id]}</span>
                  <div>
                    <b>{a.name}</b>
                    <div className="muted small">
                      {a.office}{a.link && <> · <a href={a.link} target="_blank" rel="noreferrer">{a.system}</a></>}
                    </div>
                    {a.depends_on.length > 0 && (
                      <div className="tl-after">↳ after {after(a)}</div>
                    )}
                  </div>
                </div>
                <div className="tl-track">
                  <div className="tl-span" style={{ left: pos(l), width: `calc(${pos(r)} - ${pos(l)})` }} />
                  <div className="tl-dot" style={{ left: pos(a.deadline) }} title={a.deadline_label} />
                  <div className={'tl-date' + (t(a.deadline) - start > span * 0.7 ? ' left' : '')} style={{ left: pos(a.deadline) }}>
                    {short(a.deadline)}
                    <span className="tl-days">
                      {a.color === 'done' ? ' · done' : a.days_left < 0 ? ` · ${-a.days_left}d late` : ` · ${a.days_left}d left`}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {undated.length > 0 && (
        <div className="tl-undated">
          <b className="small">No fixed deadline in our rulebook. Confirm with the office:</b>
          <ul>
            {undated.map(a => (
              <li key={a.id}>#{a.order} {a.name} <span className="muted small">· {a.office}
                {a.link && <> · <a href={a.link} target="_blank" rel="noreferrer">{a.system}</a></>}
                {a.depends_on.length > 0 && <> · after {after(a)}</>}</span></li>
            ))}
          </ul>
        </div>
      )}

      <div className="tl-legend">
        {['red', 'yellow', 'green', 'done'].map(c => <span key={c} className={'c-' + c}><i />{STATUS[c]}</span>)}
      </div>
    </div>
  )
}
