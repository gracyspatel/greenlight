// Owner: Split B. Food vendor picker that SUGGESTS, never decides.
// Shows the vendor named in the description, how it does on each vendor rule, and the
// other vendors on the list. The user picks; nothing changes until "Use this vendor".
// The list is SYNTHETIC demo data until the team has USG's real vendor list.
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import './vendors.css'

const money = n => '$' + Math.round(n || 0).toLocaleString()

// every check the rules run on a vendor, in plain words
function checks(v, cap, pp) {
  return [
    { ok: v.usg_vendor, yes: 'On the USG vendor list', no: 'Not on the USG vendor list' },
    { ok: v.catering_approved, yes: 'Approved to cater', no: 'Not approved to cater' },
    { ok: v.health_permit && v.insurance, yes: 'Health permit & insurance on file',
      no: `Missing ${[!v.health_permit && 'health permit', !v.insurance && 'insurance'].filter(Boolean).join(' & ')}` },
    { ok: (pp ?? v.per_person) <= cap, yes: `Within $${cap}/person`, no: `Over $${cap}/person` },
  ]
}
const passes = (v, cap) => checks(v, cap).every(c => c.ok)

export default function VendorPicker({ event, setEvent, result }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [onlyOk, setOnlyOk] = useState(true)
  const [q, setQ] = useState('')
  useEffect(() => { api.vendors().then(setData).catch(() => setError("Couldn't load the vendor list.")) }, [])

  const cap = data?.food_cap || 35
  const food = result?.event?.food || event.food || {}
  const current = data?.vendors.find(v => v.name === food.vendor_match)
  const foodTotal = (event.budget_lines || []).filter(l => l.category === 'food').reduce((s, l) => s + (+l.amount || 0), 0)
  const pp = event.attendance && foodTotal ? foodTotal / event.attendance : null

  const shown = useMemo(() => (data?.vendors || [])
    .filter(v => v.location !== 'Off campus')
    .filter(v => !onlyOk || passes(v, cap))
    .filter(v => !q || (v.name + ' ' + v.cuisine).toLowerCase().includes(q.toLowerCase())), [data, onlyOk, q, cap])

  const use = v => setEvent({ ...event, food: { ...(event.food || {}), served: true, vendor: v.name, vendor_approved: !!v.catering_approved } })

  return (
    <section className="card vp" aria-labelledby="vp-title">
      <h3 id="vp-title" className="vp-title">Food vendor</h3>
      {data?.synthetic && (
        <p className="vp-demo" role="note">
          <b>Demo vendor list.</b> Not USC's or USG's real list: statuses are made up for this demo.
          Confirm real vendors with usgfunds@usc.edu or Purchasing Services (213-740-2281).
        </p>
      )}
      {error && <div className="error">{error}</div>}

      <div className="vp-current">
        {!food.vendor ? (
          <p><b>No vendor named yet.</b> Pick one below so we can check it.</p>
        ) : current ? (
          <>
            <p>Your vendor: <b>{food.vendor}</b>{food.vendor !== current.name && <span className="muted"> (matched “{current.name}”)</span>}</p>
            <ul className="vp-checks">
              {checks(current, cap, pp).map(c => (
                <li key={c.yes} className={c.ok ? 'ok' : 'bad'}>
                  <span aria-hidden="true">{c.ok ? '✓' : '✕'}</span> {c.ok ? c.yes : c.no}
                  {c.yes.startsWith('Within') && pp != null && <span className="muted"> · yours: {money(foodTotal)} ÷ {event.attendance} = ${pp.toFixed(2)}</span>}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="vp-unknown">
            Your vendor: <b>{food.vendor}</b>. <span>✕ Not on our vendor list.</span> USG won't accept a vendor that isn't on its list.
          </p>
        )}
      </div>

      <div className="vp-tools">
        <label className="vp-only"><input type="checkbox" checked={onlyOk} onChange={e => setOnlyOk(e.target.checked)} /> Only vendors that pass every check</label>
        <label className="sr-only" htmlFor="vp-q">Search vendors</label>
        <input id="vp-q" value={q} onChange={e => setQ(e.target.value)} placeholder="Search (e.g. coffee, Mexican)" />
      </div>

      <ul className="vp-list">
        {shown.map(v => {
          const ok = passes(v, cap)
          const isCur = current?.name === v.name
          return (
            <li key={v.name} className={'vp-item' + (ok ? '' : ' fail') + (isCur ? ' cur' : '')}>
              <div className="vp-main">
                <b>{v.name}</b>
                <span className="muted"> · {v.cuisine} · {v.location} · ~${v.per_person}/person</span>
                <div className="vp-badges">
                  {checks(v, cap).map(c => (
                    <span key={c.yes} className={'vp-badge ' + (c.ok ? 'ok' : 'bad')}>{c.ok ? '✓' : '✕'} {c.ok ? c.yes : c.no}</span>
                  ))}
                </div>
              </div>
              {isCur
                ? <span className="muted vp-curtag">Current</span>
                : <button className={ok ? '' : 'ghost'} onClick={() => use(v)} aria-label={`Use ${v.name} as the food vendor`}>Use this vendor</button>}
            </li>
          )
        })}
        {data && !shown.length && <li className="muted">No vendors match.</li>}
      </ul>
      <p className="muted small">Changing the vendor doesn't change your food cost. Update the food line in the budget below if the price changes.</p>
    </section>
  )
}
