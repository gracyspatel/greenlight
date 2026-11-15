// Owner: Split B. Floating "Ask" button (bottom right, every page) that opens a small panel.
// "Can USG pay for T-shirts?" -> /ask. Answers come only from stored USC guideline pages,
// with a citation; otherwise it says to email USG.
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import './ask.css'

const EXAMPLES = ['Can USG pay for T-shirts?', 'How many events can USG fund?', 'Do I need vendor quotes?']

export default function AskBox() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [a, setA] = useState(null)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)
  const btnRef = useRef(null)

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const onKey = e => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const close = () => { setOpen(false); btnRef.current?.focus() }

  const ask = async question => {
    const text = (question ?? q).trim()
    if (!text) return
    setQ(text); setBusy(true); setA(null)
    try { setA(await api.ask(text)) }
    catch { setA({ answer: "Couldn't reach the rulebook. Email usgfunds@usc.edu.", citations: [] }) }
    finally { setBusy(false) }
  }

  return (
    <>
      {open && (
        <div className="ask-panel" role="dialog" aria-modal="false" aria-labelledby="ask-title" id="ask-panel">
          <div className="ask-head">
            <h2 id="ask-title">Ask the rulebook</h2>
            <button className="ghost ask-x" onClick={close} aria-label="Close">✕</button>
          </div>
          <p className="muted ask-sub">Answers come only from USC's published funding and event pages.</p>
          <form className="ask-form" onSubmit={e => { e.preventDefault(); ask() }}>
            <label htmlFor="ask-input" className="sr-only">Your question</label>
            <input id="ask-input" ref={inputRef} value={q} onChange={e => setQ(e.target.value)} placeholder="Type a question…" />
            <button disabled={!q.trim() || busy}>{busy ? 'Looking…' : 'Ask'}</button>
          </form>
          {!a && !busy && (
            <div className="ask-examples">
              <span className="muted">Try:</span>
              {EXAMPLES.map(x => <button key={x} type="button" className="ghost" onClick={() => ask(x)}>{x}</button>)}
            </div>
          )}
          <div aria-live="polite">
            {busy && <p className="muted">Searching the rules…</p>}
            {a && (
              <div className="ask-answer">
                <p>{a.answer}</p>
                {a.citations?.length > 0 && (
                  <p className="muted">
                    Source:{' '}
                    {a.citations.map((c, i) => (
                      <span key={c.source || c.title}>{i > 0 && ', '}<a href={c.source} target="_blank" rel="noreferrer">{c.title}</a></span>
                    ))}
                  </p>
                )}
                <button type="button" className="ghost" onClick={() => { setA(null); setQ(''); inputRef.current?.focus() }}>Ask another</button>
              </div>
            )}
          </div>
        </div>
      )}
      <button ref={btnRef} className="ask-fab" onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open} aria-controls="ask-panel">
        <span aria-hidden="true">?</span> {open ? 'Close' : 'Ask a question'}
      </button>
    </>
  )
}
