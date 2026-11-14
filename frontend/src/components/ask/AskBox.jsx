// Owner: Split B. "Can USG pay for T-shirts?" -> /ask, answer with citation.
// Answers come only from stored USC guideline pages; otherwise it says to email USG.
import { useState } from 'react'
import { api } from '../../api'

const EXAMPLES = ['Can USG pay for T-shirts?', 'How many events can USG fund?', 'Do I need vendor quotes?']

export default function AskBox() {
  const [q, setQ] = useState('')
  const [a, setA] = useState(null)
  const [busy, setBusy] = useState(false)

  const ask = async question => {
    const text = (question ?? q).trim()
    if (!text) return
    setQ(text); setBusy(true); setA(null)
    try { setA(await api.ask(text)) }
    catch { setA({ answer: "Couldn't reach the rulebook. Email usgfunds@usc.edu.", citations: [] }) }
    finally { setBusy(false) }
  }

  return (
    <div className="card">
      <h2>Ask the rulebook</h2>
      <form className="row" onSubmit={e => { e.preventDefault(); ask() }}>
        <input style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} placeholder="Can USG pay for T-shirts?" />
        <button disabled={!q.trim() || busy}>{busy ? 'Looking…' : 'Ask'}</button>
      </form>
      {!a && !busy && (
        <div className="row">
          {EXAMPLES.map(x => <button key={x} type="button" className="ghost" style={{ fontSize: 13, padding: '4px 8px' }} onClick={() => ask(x)}>{x}</button>)}
        </div>
      )}
      {a && (
        <div style={{ marginTop: 8 }}>
          <p style={{ margin: '0 0 6px' }}>{a.answer}</p>
          {a.citations?.length > 0 && (
            <div className="muted">
              Source:{' '}
              {a.citations.map((c, i) => (
                <span key={c.source || c.title}>{i > 0 && ', '}<a href={c.source} target="_blank" rel="noreferrer">{c.title}</a></span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
