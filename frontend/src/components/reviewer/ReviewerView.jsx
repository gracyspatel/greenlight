// Owner: Split B. USG reviewer queue of pre-checked applications.
import { useEffect, useState } from 'react'
import { api } from '../../api'
export default function ReviewerView() {
  const [rows, setRows] = useState([])
  useEffect(() => { api.reviewerQueue().then(setRows).catch(() => setRows([])) }, [])
  return (
    <div className="card">
      <h2>USG review queue</h2>
      <table><thead><tr><th>Event</th><th>Date</th><th>Requested</th><th>Rule check</th><th>Summary</th></tr></thead>
        <tbody>{rows.map(r => (
          <tr key={r.id}><td>{r.name}</td><td>{r.date}</td><td>${r.requested}</td>
            <td><span className={'pill ' + r.verdict}>{r.verdict_label}</span></td><td>{r.summary}</td></tr>
        ))}</tbody></table>
    </div>
  )
}
