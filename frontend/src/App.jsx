// App shell. Owner: Split B. Holds the ONE source of truth: `event`.
// Every component gets `event` / `result` as props and calls `setEvent(newEvent)`
// to change it; the shell re-runs /check automatically (this IS the fix loop).
import { useEffect, useState } from 'react'
import { api } from './api'
import IntakePanel from './components/intake/IntakePanel'
import Timeline from './components/timeline/Timeline'
import VerdictCards from './components/verdict/VerdictCards'
import FixPanel from './components/fixloop/FixPanel'
import Tracker from './components/tracker/Tracker'
import PackView from './components/pack/PackView'
import ReviewerView from './components/reviewer/ReviewerView'
import AskBox from './components/ask/AskBox'

export default function App() {
  const [view, setView] = useState('officer')
  const [event, setEvent] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!event) return
    let live = true // ignore answers to older edits that arrive late
    api.check(event)
      .then(r => { if (live) { setResult(r); setError('') } })
      .catch(() => live && setError("Couldn't reach the rule checker. Is the backend running?"))
    return () => { live = false }
  }, [event])

  return (
    <div className="app">
      <header>
        <h1>🟢 Greenlight</h1>
        <nav>
          <button className={view === 'officer' ? 'on' : ''} onClick={() => setView('officer')}>Club officer</button>
          <button className={view === 'reviewer' ? 'on' : ''} onClick={() => setView('reviewer')}>USG reviewer</button>
        </nav>
      </header>
      {error && <div className="error">{error}</div>}
      {view === 'reviewer' ? <main className="single"><ReviewerView /></main> : (
        <main>
          <section className="left">
            <IntakePanel event={event} setEvent={setEvent} questions={result?.questions || []} />
            {event && <FixPanel event={event} setEvent={setEvent} result={result} />}
            <AskBox />
          </section>
          <section className="right">
            {result && <VerdictCards result={result} event={event} />}
            {result && <Timeline result={result} />}
            {result && <Tracker result={result} event={event} setEvent={setEvent} />}
            {result && <PackView result={result} event={event} onSubmitted={() => setView('reviewer')} />}
          </section>
        </main>
      )}
    </div>
  )
}
