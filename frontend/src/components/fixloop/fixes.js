// Owner: Split A. "Apply fix" actions for engine flags.
// The frontend never guesses a number or date: every suggested value is found by
// asking the engine (/check) which values pass, so the rules still decide.
import { api } from '../../api'

const iso = d => d.toISOString().slice(0, 10)
export const addDays = (s, n) => { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d) }
const todayOf = ev => ev.as_of || iso(new Date())
const flagged = (res, pred) => !!res && res.approvals.some(a => a.flags.some(pred))
const isDateFlag = f => /_(deadline|breaks)$/.test(f.rule_id)
const money = n => '$' + Math.round(n).toLocaleString()

export function semesterOf(date) {
  if (!date) return 'this semester'
  const [y, m] = date.split('-').map(Number)
  return (m <= 5 ? 'Spring ' : m <= 7 ? 'Summer ' : 'Fall ') + y
}

export function prettyDate(date) {
  if (!date) return ''
  return new Date(date + 'T00:00:00Z').toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

/** First event date (after the current one) where no approval has a deadline or break problem. */
export async function findWorkingDate(ev) {
  const from = [todayOf(ev), ev.date].filter(Boolean).sort().at(-1)
  for (let off = 1; off <= 300; off += 30) {
    const dates = Array.from({ length: 15 }, (_, i) => addDays(from, off + i * 2))
    const res = await Promise.all(dates.map(date => api.check({ ...ev, date }).catch(() => null)))
    const i = res.findIndex(r => r && !flagged(r, isDateFlag))
    if (i >= 0) return dates[i]
  }
  return null
}

/** Largest whole-dollar x in [0, hi] where `set(ev, x)` no longer triggers `ruleId`. */
async function largestPassing(ev, hi, set, ruleId) {
  const fails = async x => flagged(await api.check(set(ev, x)).catch(() => null), f => f.rule_id === ruleId)
  if (await fails(0)) return null
  let lo = 0
  hi = Math.floor(hi)
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (await fails(mid)) hi = mid - 1; else lo = mid
  }
  return lo
}

const setPath = (ev, path, value) => {
  const e = structuredClone(ev)
  let o = e; const keys = path.split('.')
  keys.slice(0, -1).forEach(k => { o[k] = o[k] || {}; o = o[k] })
  o[keys.at(-1)] = value
  return e
}
const deepPatch = (ev, patch) => Object.entries(patch).reduce((e, [k, v]) => setPath(e, k, v), ev)

const DROP = {
  social_dance_start: { key: 'drop-dancing', label: 'Drop dancing', run: ev => ({ ...ev, dancing: false }) },
  social_dance_form: { key: 'drop-dancing', label: 'Drop dancing', run: ev => ({ ...ev, dancing: false }) },
  fundraising_ca: { key: 'drop-tickets', label: 'Stop selling tickets', run: ev => ({ ...ev, ticket_sales: false }) },
  fundraising_bh: { key: 'drop-tickets', label: 'Stop selling tickets', run: ev => ({ ...ev, ticket_sales: false }) },
}

/**
 * Fix actions for one flag: [{key, label, run(ev) -> Promise<newEvent|null>, focus?, note?}].
 * `key` lets the panel merge the same action across flags (e.g. one date move fixes 4 deadlines).
 */
export function fixesFor(flag, approval, ev) {
  const out = []
  const id = flag.rule_id
  if (flag.patch && typeof flag.patch === 'object') {
    out.push({ key: 'patch-' + id, label: 'Apply suggested fix', run: async e => deepPatch(e, flag.patch) })
  }
  if (/_(deadline|breaks)$/.test(id)) {
    out.push({
      key: 'move-date', label: 'Find a date that works',
      run: async e => { const d = await findWorkingDate(e); return d ? { ...e, date: d } : null },
      fail: 'No date in the next 10 months clears every deadline. Try dropping a feature.',
    })
  }
  if (/_(deadline|order)$/.test(id) && DROP[approval.id]) out.push(DROP[approval.id])

  switch (id) {
    case 'usg_annual_cap': {
      out.push({
        key: 'cap-request', label: 'Lower the request to the most that passes',
        run: async e => { const x = await largestPassing(e, e.amount_requested || 0, (v, n) => ({ ...v, amount_requested: n }), id); return x == null ? null : { ...e, amount_requested: x } },
        fail: "Lowering this request alone can't clear it: this year's earlier USG money is already too high.",
      })
      break
    }
    case 'usg_venue_cap': {
      out.push({
        key: 'cap-venue', label: 'Cut the venue cost to the most that passes',
        run: async e => {
          const lines = e.budget_lines || []
          const venue = lines.map((l, i) => [l, i]).filter(([l]) => l.category === 'venue').sort((a, b) => b[0].amount - a[0].amount)
          if (!venue.length) return null
          const i = venue[0][1]
          const setLine = (v, n) => ({ ...v, budget_lines: v.budget_lines.map((l, j) => (j === i ? { ...l, amount: n } : l)) })
          const x = await largestPassing(e, lines[i].amount, setLine, id)
          return x == null ? null : setLine(e, x)
        },
        fail: 'Cutting the biggest venue line alone is not enough. Edit the budget lines below.',
      })
      break
    }
    case 'usg_event_cap': {
      const sem = semesterOf(ev.date)
      if (sem !== semesterOf(todayOf(ev))) {
        out.push({ key: 'event-count', label: `Enter your ${sem} count`, focus: 'fix-funded-events',
          note: `Your event is now in ${sem}. Enter how many events USG has funded for your club in that semester.` })
      } else {
        out.push({ key: 'event-count-note', label: 'Move the date to next semester', focus: 'fix-date',
          note: "USG counts funded events per semester. Pick a date in next semester, then enter that semester's count." })
      }
      out.push({ key: 'no-usg', label: 'Fund it another way (no USG request)', run: async e => ({ ...e, funding_source: 'none' }) })
      break
    }
    case 'gsg_vendor_quotes':
      out.push({ key: 'quotes', label: "I've attached every quote",
        run: async e => ({ ...e, budget_lines: (e.budget_lines || []).map(l => ({ ...l, quote_attached: true })) }) })
      break
    case 'food_vendor':
      out.push({ key: 'food-free', label: 'Give the food away free', run: async e => setPath(e, 'food.sold', false) })
      out.push({ key: 'food-usc', label: 'Switch to USC Hospitality',
        run: async e => setPath(setPath(e, 'food.vendor', 'USC Hospitality'), 'food.vendor_approved', true) })
      break
    case 'uepa_needs_venue':
      out.push({ key: 'venue-ok', label: 'My venue is confirmed', run: async e => setPath(e, 'venue.confirmed', true) })
      break
    default:
  }
  return out
}

/** All fix actions for a check result, merged by key: [{key,label,run,..., flags:[{flag, approval}]}]. */
export function allFixes(result, ev) {
  const byKey = new Map()
  for (const a of result.approvals) {
    for (const f of a.flags) {
      for (const fx of fixesFor(f, a, ev)) {
        if (!byKey.has(fx.key)) byKey.set(fx.key, { ...fx, flags: [] })
        byKey.get(fx.key).flags.push({ flag: f, approval: a })
      }
    }
  }
  const rank = f => Math.min(...f.flags.map(x => (x.flag.level === 'reject' ? 0 : 1)))
  return [...byKey.values()].sort((x, y) => rank(x) - rank(y) || y.flags.length - x.flags.length)
}

export { money }
