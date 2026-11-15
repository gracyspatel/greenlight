// Owner: Split B. Category summary + the "Warning" list.
// Warning = a risk factor the club can't change (USG funds running low, a break in the
// deadline window, close to the yearly cap...). Shown so nobody is surprised; never blocks Ready.
import './warnings.css'

// Ready counts approvals that pass, including ones that only carry warnings.
export function Summary({ result }) {
  const c = result.counts || {}
  const tiles = [
    { k: 'reject', n: c.reject || 0, label: 'Will be rejected', sub: 'must change', icon: '✕' },
    { k: 'risk', n: c.risk || 0, label: 'At risk', sub: 'you can fix', icon: '!' },
    { k: 'ready', n: (c.ready || 0) + (c.warning || 0), label: 'Ready', sub: 'passes the rules', icon: '✓' },
    { k: 'warning', n: result.warnings?.length || 0, label: 'Warnings', sub: "can't be changed", icon: '⚠' },
  ]
  return (
    <ul className="wn-summary" aria-label="Summary of your approvals">
      {tiles.map(t => (
        <li key={t.k} className={'wn-tile ' + t.k + (t.n === 0 ? ' zero' : '')}>
          <span className="wn-icon" aria-hidden="true">{t.icon}</span>
          <span className="wn-n">{t.n}</span>
          <span className="wn-label">{t.label}<small>{t.sub}</small></span>
        </li>
      ))}
    </ul>
  )
}

export function Warnings({ result }) {
  const list = result.warnings || []
  if (!list.length) return null
  return (
    <section className="card wn-card" aria-labelledby="wn-title">
      <h3 id="wn-title"><span aria-hidden="true">⚠</span> Things to keep in mind</h3>
      <p className="muted wn-sub">
        These are risk factors you can't change. They don't stop you from being Ready, but plan around them.
      </p>
      <ul className="wn-list">
        {list.map(w => (
          <li key={w.approval_id + w.rule_id}>
            <div><span className="muted">{w.approval}:</span> <b>{w.message}</b></div>
            {w.fix && <div className="wn-tip">What you can do: {w.fix}</div>}
            {w.source && (
              <div className="wn-src muted">
                Rule: “{w.rule_text}” <a href={w.source} target="_blank" rel="noreferrer">source</a>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
