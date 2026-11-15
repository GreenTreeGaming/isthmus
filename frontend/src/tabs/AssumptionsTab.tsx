import { useEffect, useState } from 'react'
import { getAssumptions } from '../api'
import type { Assumptions } from '../types'

export function AssumptionsTab() {
  const [data, setData] = useState<Assumptions | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAssumptions()
      .then((r) => setData(r.data))
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <div className="page"><div className="error-box">Could not load assumptions: {error}</div></div>
  if (!data) return <div className="page"><div className="loading-box"><span className="spinner" /> Loading…</div></div>

  return (
    <div className="page assumptions">
      <header className="page-head">
        <div>
          <h2>Assumptions &amp; limitations</h2>
          <p className="muted">Every number the model depends on, in one place. Each one is tunable in <code>engine/assumptions.py</code>.</p>
        </div>
        {data.source === 'placeholder' && <span className="badge warn">Draft values — engine not connected yet</span>}
      </header>

      <nav className="spec-toc" aria-label="Sections">
        {data.groups.map((g) => (
          <a key={g.title} href={`#spec-${g.title}`}>{g.title}</a>
        ))}
      </nav>

      {data.groups.map((g) => (
        <section key={g.title} id={`spec-${g.title}`} className="spec">
          <h3>{g.title}</h3>
          <table className="spec-table">
            <thead>
              <tr>
                <th scope="col">Parameter</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {g.items.map((it) => {
                const text = String(it.value)
                const long = text.length > 18
                return (
                  <tr key={it.name}>
                    <th scope="row">
                      <span className="spec-name">{it.name}</span>
                      {it.note && <span className="spec-note">{it.note}</span>}
                      {it.key && <code className="const-key">{it.key}</code>}
                    </th>
                    <td className={long ? 'spec-long' : ''}>
                      {long && text.includes(' · ') ? (
                        <span className="val-list">
                          {text.split(' · ').map((part) => {
                            const [k, v] = part.split(': ')
                            return v == null ? <code key={part} className="val">{part}</code> : (
                              <span key={part} className="val-pair"><span>{k}</span><code className="val">{v}</code></span>
                            )
                          })}
                        </span>
                      ) : long ? <span className="spec-text">{text}</span> : <code className="val">{text}</code>}
                      {it.unit && <span className="unit"> {it.unit}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      ))}

      <div className="assume-grid two">
        <section className="assume-card">
          <h3>Data sources</h3>
          <dl>
            {data.data_sources.map((d) => (
              <div key={d.name} className="assume-row">
                <dt>{d.name}</dt>
                <dd className="text">{d.detail}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="assume-card">
          <h3>Limitations</h3>
          <ul className="limits">
            {data.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
