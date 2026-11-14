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
import ReviewerView from './components/reviewer/ReviewerView'
import AskBox from './components/ask/AskBox'

export default function App() {
  const [view, setView] = useState('officer')
  const [event, setEvent] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!event) return
    api.check(event).then(r => { setResult(r); setError('') }).catch(e => setError(String(e)))
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
      {view === 'reviewer' ? <ReviewerView /> : (
        <main>
          <section className="left">
            <IntakePanel event={event} setEvent={setEvent} questions={result?.questions || []} />
            {event && <FixPanel event={event} setEvent={setEvent} />}
            <AskBox />
          </section>
          <section className="right">
            {result && <VerdictCards result={result} event={event} />}
            {result && <Timeline result={result} />}
            {result && <Tracker result={result} event={event} setEvent={setEvent} />}
          </section>
        </main>
      )}
    </div>
  )
}
