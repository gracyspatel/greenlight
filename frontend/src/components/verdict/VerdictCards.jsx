// Owner: Split A. Overall verdict banner + one card per approval with its flags.
// TODO(Split A): "Explain" button per flag -> api.explain(flag) and show reason/fix/quote/source.
const CLS = { ready: 'ready', risk: 'risk', reject: 'reject' }
export default function VerdictCards({ result }) {
  return (
    <div className="card">
      <div className={'banner ' + CLS[result.verdict]}>
        <h2>{result.verdict_label}</h2>
        <small>{result.disclaimer}</small>
      </div>
      {result.approvals.map(a => (
        <div key={a.id} className={'approval ' + CLS[a.verdict]}>
          <div className="row"><b>{a.name}</b><span className="pill">{a.verdict_label}</span></div>
          {a.flags.map(f => (
            <div key={f.rule_id} className="flag">
              <div>⚠️ {f.message}</div>
              <div><b>Fix:</b> {f.fix}</div>
              <div className="muted">Rule: “{f.rule_text}” <a href={f.source} target="_blank">source</a></div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
