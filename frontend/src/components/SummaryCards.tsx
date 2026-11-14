import type { Summary } from '../types'
import { fmtCompact, fmtDuration, fmtInt } from '../lib/format'

interface Props {
  summary: Summary | null
  loading: boolean
}

export function SummaryCards({ summary: s, loading }: Props) {
  const served = s ? s.need_bus_total - s.need_bus_unserved : 0
  const servedPct = s && s.need_bus_total > 0 ? served / s.need_bus_total : 1
  return (
    <div className={`cards ${loading ? 'stale' : ''}`}>
      <div className="card hero-card">
        <div className="card-label">Everyone out in</div>
        <div className="card-value">{!s ? '—' : s.people_evacuating > 0 ? fmtDuration(s.sim_clearance_s) : 'No one leaves'}</div>
        <div className="card-sub keep">
          {s && s.people_evacuating > 0 ? `from alert · driving time ${fmtDuration(s.clearance_time_s)}` : 'from alert until the last car is out'}
        </div>
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot evac" /> Evacuating
        </div>
        <div className="card-value">{s ? fmtCompact(s.people_evacuating) : '—'}</div>
        <div className="card-sub">people</div>
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot shelter" /> Sheltering
        </div>
        <div className="card-value">{s ? fmtCompact(s.people_sheltering) : '—'}</div>
        <div className="card-sub">people, in place</div>
      </div>
      <div className="card wide">
        <div className="card-label">
          <i className="dot bus" /> Need a bus
        </div>
        <div className="card-value">
          {s ? fmtInt(s.need_bus_total) : '—'}
          {s && s.need_bus_unserved > 0 && <span className="bad small"> · {fmtInt(s.need_bus_unserved)} unserved</span>}
        </div>
        <div className="meter" aria-label={`${Math.round(servedPct * 100)}% picked up before the plume`}>
          <span style={{ width: `${servedPct * 100}%` }} />
        </div>
        <div className="card-sub">{s ? `${Math.round(servedPct * 100)}% picked up before plume arrives` : ' '}</div>
      </div>
      <div className="card narrow">
        <div className="card-label">Runtime</div>
        <div className="card-value mono">{s ? `${fmtInt(s.runtime_ms)}` : '—'}<small> ms</small></div>
        <div className="card-sub">{s ? `${s.bottleneck_edge_ids.length} bottleneck${s.bottleneck_edge_ids.length === 1 ? '' : 's'}` : ' '}</div>
      </div>
    </div>
  )
}
