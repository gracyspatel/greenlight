// App shell. Owner: Split B. Holds the ONE source of truth: `event`.
// Every component gets `event` / `result` as props and calls `setEvent(newEvent)`
// to change it; the shell re-runs /check automatically (this IS the fix loop).
//
// The officer view is a 5-step flow, one thing per screen:
//   1 Describe → 2 What you need → 3 Fix problems → 4 Submit → 5 Track
// A status bar keeps the current verdict visible on every step.
import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import IntakePanel from './components/intake/IntakePanel'
import Timeline from './components/timeline/Timeline'
import VerdictCards from './components/verdict/VerdictCards'
import FixPanel from './components/fixloop/FixPanel'
import DateCalendar from './components/calendar/DateCalendar'
import Tracker from './components/tracker/Tracker'
import PackView from './components/pack/PackView'
import ReviewerView from './components/reviewer/ReviewerView'
import AskBox from './components/ask/AskBox'
import { Summary, Warnings } from './components/warnings/Warnings'
import './shell.css'

const STEPS = [
  { id: 'describe', title: 'Describe your event', short: 'Describe',
    hint: 'Tell us about your event in your own words, or try one of the examples.' },
  { id: 'needs', title: 'See what you need', short: 'What you need',
    hint: "Every approval your event needs, its deadline, and whether it meets USC's written rules." },
  { id: 'fix', title: 'Fix problems', short: 'Fix',
    hint: 'Pick a date that works and fix each problem. We only suggest; you decide every change.' },
  { id: 'submit', title: 'Submit your forms', short: 'Submit',
    hint: 'Drafted text for each form, ready to copy into the right system.' },
  { id: 'track', title: 'Track your approvals', short: 'Track',
    hint: 'Mark each approval as you submit it and hear back. We’ll show what’s blocking you.' },
]
const ICON = { ready: '✓', risk: '!', reject: '✕' }

export default function App() {
  const [view, setView] = useState('officer')
  const [step, setStep] = useState(0)
  const [event, setEvent] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const headingRef = useRef(null)
  const moved = useRef(false)

  useEffect(() => {
    if (!event) return
    let live = true // ignore answers to older edits that arrive late
    api.check(event)
      .then(r => { if (live) { setResult(r); setError('') } })
      .catch(() => live && setError("Couldn't reach the rule checker. Is the backend running?"))
    return () => { live = false }
  }, [event])

  // move focus to the new step's heading so keyboard and screen-reader users land in the right place
  useEffect(() => {
    if (!moved.current) { moved.current = true; return }
    window.scrollTo({ top: 0, behavior: 'smooth' })
    headingRef.current?.focus({ preventScroll: true })
  }, [step, view])

  const go = i => setStep(Math.max(0, Math.min(STEPS.length - 1, i)))
  const unlocked = i => i === 0 || !!result
  const problems = result ? (result.counts?.reject || 0) + (result.counts?.risk || 0) : 0
  const warnings = result?.warnings?.length || 0
  const s = STEPS[step]

  return (
    <div className="app gl">
      <a href="#main" className="gl-skip">Skip to content</a>
      <header className="gl-header">
        <h1><span aria-hidden="true">🟢</span> Greenlight</h1>
        <nav aria-label="View">
          <button className={view === 'officer' ? 'on' : ''} aria-pressed={view === 'officer'} onClick={() => setView('officer')}>Club officer</button>
          <button className={view === 'reviewer' ? 'on' : ''} aria-pressed={view === 'reviewer'} onClick={() => setView('reviewer')}>USG reviewer</button>
        </nav>
      </header>
      {error && <div className="error" role="alert">{error}</div>}

      {view === 'reviewer' ? (
        <main id="main" className="single" tabIndex={-1} ref={headingRef}><ReviewerView /></main>
      ) : (
        <>
          <nav className="gl-stepper" aria-label="Progress">
            <ol>
              {STEPS.map((x, i) => (
                <li key={x.id} className={i === step ? 'now' : i < step ? 'done' : ''}>
                  <button onClick={() => go(i)} disabled={!unlocked(i)} aria-current={i === step ? 'step' : undefined}
                    aria-label={`Step ${i + 1}: ${x.title}${i < step ? ' (visited)' : ''}`}>
                    <span className="gl-num" aria-hidden="true">{i < step ? '✓' : i + 1}</span>
                    <span className="gl-lbl">{x.short}</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>

          {result && (
            <div className={'gl-status ' + result.verdict} role="status" aria-live="polite">
              <span className="gl-status-icon" aria-hidden="true">{ICON[result.verdict]}</span>
              <span className="gl-status-text">
                <b>{result.verdict_label}</b>
                <span className="gl-status-ev"> · {result.event?.name}{result.event?.date ? ` · ${result.event.date}` : ''}</span>
                {problems > 0 && <span> · {problems} approval{problems === 1 ? '' : 's'} need{problems === 1 ? 's' : ''} attention</span>}
                {warnings > 0 && <span className="gl-status-warn"> · ⚠ {warnings} warning{warnings === 1 ? '' : 's'}</span>}
              </span>
              {problems > 0 && step !== 2 && <button className="gl-status-btn" onClick={() => go(2)}>Fix problems</button>}
            </div>
          )}

          <main id="main" className="gl-main">
            <section className={'gl-step step-' + s.id} aria-labelledby="gl-step-title">
              <div className="gl-step-head">
                <p className="gl-eyebrow">Step {step + 1} of {STEPS.length}</p>
                <h2 id="gl-step-title" tabIndex={-1} ref={headingRef}>{s.title}</h2>
                <p className="gl-hint">{s.hint}</p>
              </div>

              {s.id === 'describe' && (
                <IntakePanel event={event} setEvent={setEvent} questions={result?.questions || []} />
              )}

              {s.id === 'needs' && result && (
                <>
                  <Summary result={result} />
                  <Warnings result={result} />
                  <VerdictCards result={result} event={event} />
                  <Timeline result={result} />
                </>
              )}

              {s.id === 'fix' && result && (
                <>
                  {result.verdict_label === 'Needs info' ? (
                    <div className="gl-allclear needs-info">
                      <b>We need a few more facts before we can call this Ready:</b>
                      <ul>{(result.questions || []).map(q => <li key={q}>{q}</li>)}</ul>
                      Fill them in below, or answer them in step 1.
                    </div>
                  ) : problems === 0 && (
                    <div className="gl-allclear">
                      <b>✓ Nothing to fix.</b> Your event meets every written rule we check. You can still change anything below.
                    </div>
                  )}
                  <DateCalendar event={event} setEvent={setEvent} />
                  {/* always shown, so a fix can be undone or a feature added back */}
                  <FixPanel event={event} setEvent={setEvent} result={result} />
                </>
              )}

              {s.id === 'submit' && result && (
                <PackView result={result} event={event} onSubmitted={() => setView('reviewer')} />
              )}

              {s.id === 'track' && result && (
                <Tracker result={result} event={event} setEvent={setEvent} />
              )}
            </section>

            <div className="gl-footer">
              {step > 0
                ? <button className="ghost" onClick={() => go(step - 1)}>← Back</button>
                : <span />}
              {step < STEPS.length - 1 && (
                <button onClick={() => go(step + 1)} disabled={!unlocked(step + 1)}>
                  Next: {STEPS[step + 1].short} →
                </button>
              )}
            </div>
            {!result && step === 0 && <p className="muted gl-footnote">Describe your event first to unlock the next steps.</p>}
          </main>
        </>
      )}
      <AskBox />
    </div>
  )
}
