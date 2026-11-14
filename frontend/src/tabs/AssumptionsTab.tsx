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
          <p className="muted">Every number the model depends on, in one place. Change them in <code>engine/assumptions.py</code>.</p>
        </div>
        {data.source === 'placeholder' && <span className="badge warn">Draft values — engine not connected yet</span>}
      </header>

      <div className="assume-grid">
        {data.groups.map((g) => (
          <section key={g.title} className="assume-card">
            <h3>{g.title}</h3>
            <dl>
              {g.items.map((it) => (
                <div key={it.name} className="assume-row">
                  <dt>
                    {it.name}
                    {it.note && <small>{it.note}</small>}
                  </dt>
                  <dd className={typeof it.value === 'string' && it.value.length > 14 ? 'long' : 'mono'}>
                    {String(it.value)}
                    {it.unit && <span className="unit"> {it.unit}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>

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
