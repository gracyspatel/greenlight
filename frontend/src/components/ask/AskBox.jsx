// Owner: Split B. "Can USG pay for T-shirts?" -> /ask, answer with citation.
import { useState } from 'react'
import { api } from '../../api'
export default function AskBox() {
  const [q, setQ] = useState(''); const [a, setA] = useState(null)
  return (
    <div className="card">
      <h2>Ask the rulebook</h2>
      <div className="row">
        <input style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} placeholder="Can USG pay for T-shirts?" />
        <button onClick={() => api.ask(q).then(setA)} disabled={!q}>Ask</button>
      </div>
      {a && <p>{a.answer} {a.citations?.map(c => <a key={c.source} href={c.source} target="_blank"> [{c.title}]</a>)}</p>}
    </div>
  )
}
