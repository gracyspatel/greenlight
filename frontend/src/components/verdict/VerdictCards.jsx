// Owner: Split A. Overall verdict + one collapsible card per approval with its flags.
// - "Explain" asks /explain to reword a flag; the quote + source always come from the rule.
// - Before/after: after a change, flags that disappeared show as "fixed", new ones as "new".
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import './verdict.css'

const ICON = { ready: '✓', risk: '!', reject: '✕' }
const LABEL = { ready: 'Ready', risk: 'At risk', reject: 'Will be rejected' }
const keyOf = (a, f) => a.id + '/' + f.rule_id

export default function VerdictCards({ result, event }) {
  const prev = useRef(null)
  const [diff, setDiff] = useState(null)
  const [open, setOpen] = useState({})

  // before/after: compare with the previous result for the SAME event
  useEffect(() => {
    const p = prev.current
    prev.current = result
    if (!p || p.event?.name !== result.event?.name) { setDiff(null); return }
    const before = new Map(p.approvals.flatMap(a => a.flags.map(f => [keyOf(a, f), { a, f }])))
    const now = new Set(result.approvals.flatMap(a => a.flags.map(f => keyOf(a, f))))
    const fixed = [...before].filter(([k]) => !now.has(k)).map(([, v]) => v)
    const added = new Set([...now].filter(k => !before.has(k)))
    if (!fixed.length && !added.size && p.verdict === result.verdict) return
    setDiff({ fixed, added, from: p.verdict_label, changed: p.verdict !== result.verdict })
  }, [result])

  const isOpen = a => open[a.id] ?? a.verdict !== 'ready'
  const toggle = a => setOpen(o => ({ ...o, [a.id]: !isOpen(a) }))

  return (
    <div className="card verdict">
      <div className={'banner big ' + result.verdict}>
        <div className="banner-top">
          <span className="v-icon">{ICON[result.verdict]}</span>
          <div>
            <div className="muted small">{result.event?.name} · {result.event?.date || 'no date yet'}</div>
            <h2>
              {diff?.changed && <span className="was">{diff.from} → </span>}
              {result.verdict_label}
            </h2>
          </div>
        </div>
        <div className="chips">
          {['reject', 'risk', 'ready'].map(k => (
            <span key={k} className={'chip ' + k}><b>{result.counts?.[k] ?? 0}</b> {LABEL[k]}</span>
          ))}
        </div>
        <small className="disclaimer">{result.disclaimer}</small>
      </div>

      {diff?.fixed.length > 0 && (
        <div className="fixed-strip" key={result.event?.date + diff.fixed.length}>
          <b>✓ Fixed by your last change</b>
          <ul>{diff.fixed.map(({ a, f }) => <li key={keyOf(a, f)}><span className="muted">{a.name}:</span> {f.message}</li>)}</ul>
        </div>
      )}

      {result.approvals.map(a => (
        <div key={a.id} className={'approval ' + a.verdict + (isOpen(a) ? ' open' : '')}>
          <button className="approval-head" onClick={() => toggle(a)} aria-expanded={isOpen(a)}>
            <span className="caret">{isOpen(a) ? '▾' : '▸'}</span>
            <b>{a.name}</b>
            <span className="muted small">{a.office}</span>
            <span className={'pill ' + a.verdict}>{a.verdict_label}{a.flags.length > 0 && ` · ${a.flags.length}`}</span>
          </button>
          {isOpen(a) && (
            <div className="approval-body">
              <div className="muted small">
                Due {a.deadline_label}
                {a.status !== 'not_started' && <> · status: {a.status.replace('_', ' ')}</>}
                {a.link && <> · <a href={a.link} target="_blank" rel="noreferrer">{a.system}</a></>}
              </div>
              {a.flags.length === 0 && <div className="flag ok">✓ Passes every rule we check.</div>}
              {a.flags.map(f => <Flag key={f.rule_id} flag={f} event={event} isNew={diff?.added.has(keyOf(a, f))} />)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function Flag({ flag, event, isNew }) {
  const [ex, setEx] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setEx(null) }, [flag.message, flag.fix])

  const explain = async () => {
    if (ex) { setEx(null); return }
    setBusy(true)
    try {
      const r = await api.explain(flag, event)
      setEx({ reason: r.reason || flag.message, fix: r.fix || flag.fix, by: r.by || 'rules' })
    } catch {
      setEx({ reason: flag.message, fix: flag.fix, by: 'rules' })
    } finally { setBusy(false) }
  }

  return (
    <div className={'flag ' + flag.level + (isNew ? ' new' : '')}>
      <div className="flag-top">
        <span className={'lvl ' + flag.level}>{flag.level === 'reject' ? 'Blocker' : 'Risk'}</span>
        <span className="flag-msg">{flag.message}</span>
        {isNew && <span className="new-tag">new</span>}
      </div>
      <div className="flag-fix"><b>Fix:</b> {flag.fix}</div>
      <div className="flag-actions">
        <button className="ghost small" onClick={explain} disabled={busy}>{busy ? 'Explaining…' : ex ? 'Hide explanation' : 'Explain'}</button>
      </div>
      {ex && (
        <div className="explain">
          <p>{ex.reason}</p>
          <p><b>What to do:</b> {ex.fix}</p>
          <blockquote>“{flag.rule_text}”</blockquote>
          <div className="muted small">
            {flag.source && <a href={flag.source} target="_blank" rel="noreferrer">Source</a>}
            {' · '}{ex.by === 'ai' ? 'Reworded by AI, checked against the rule text' : 'From our rulebook'}
          </div>
        </div>
      )}
    </div>
  )
}
