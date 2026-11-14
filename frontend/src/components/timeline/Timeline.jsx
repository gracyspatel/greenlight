// Owner: Split A. Checklist + backward timeline. Colors come from approval.color:
// red (past due) / yellow (≤7 days) / green / done / none.
// TODO(Split A): real horizontal timeline from today -> event date, show depends_on order arrows.
export default function Timeline({ result }) {
  return (
    <div className="card">
      <h2>Approval timeline</h2>
      <p className="muted">Event: {result.event.date} · checked as of {result.as_of}</p>
      <ol className="timeline">
        {result.approvals.map(a => (
          <li key={a.id} className={'dot-' + a.color}>
            <b>{a.deadline_label}</b> — {a.name}
            <span className="muted"> · {a.office} · <a href={a.link} target="_blank">{a.system}</a></span>
            {a.depends_on.length > 0 && <span className="muted"> · after {a.depends_on.join(', ')}</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}
