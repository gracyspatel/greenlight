// Shared API client. Owner: Split B. Add a function here when you add an endpoint.
// Set VITE_MOCK=1 in frontend/.env.local to work with no backend running.
import mockChecks from './mock/check_responses.json'
import mockDemos from './mock/demo_events.json'

const MOCK = import.meta.env.VITE_MOCK === '1'
const post = (url, body) =>
  fetch('/api' + url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(r => { if (!r.ok) throw new Error(url + ' ' + r.status); return r.json() })
const get = url => fetch('/api' + url).then(r => { if (!r.ok) throw new Error(url + ' ' + r.status); return r.json() })

const mockPack = result => (result.approvals || []).map(a => ({
  approval_id: a.id, name: a.name, system: a.system, link: a.link, deadline_label: a.deadline_label,
  draft: `Event: ${result.event?.name}\nDate: ${result.event?.date}`, by: 'template',
}))

export const api = {
  demos: () => (MOCK ? Promise.resolve(mockDemos) : get('/demo')),
  demo: id => (MOCK ? Promise.resolve(mockDemos.find(d => d.id === id)) : get('/demo/' + id)),
  check: event => (MOCK ? Promise.resolve(mockChecks[event.id] || mockChecks.blockers) : post('/check', event)),
  extract: (text, event) => (MOCK ? Promise.resolve({ event: mockDemos[2], questions: [] }) : post('/extract', { text, event })),
  explain: (flag, event) => (MOCK ? Promise.resolve({ reason: flag.message, fix: flag.fix, quote: flag.rule_text }) : post('/explain', { flag, event })),
  vendors: () => (MOCK ? Promise.resolve({ synthetic: true, vendors: [] }) : get('/vendors')),
  calendar: (event, start, days = 42) => (MOCK ? Promise.resolve([]) : post('/calendar', { event, start, days })),
  pack: result => (MOCK ? Promise.resolve(mockPack(result)) : post('/pack', result)),
  ask: question => (MOCK ? Promise.resolve({ answer: 'Mock mode: no answer.', citations: [] }) : post('/ask', { question })),
}
