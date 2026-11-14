import type { Summary } from '../types'
import { fmtCompact, fmtDuration, fmtInt } from '../lib/format'

export interface Pinned {
  summary: Summary
  label: string
}

interface Props {
  summary: Summary | null
  loading: boolean
  pinned: Pinned | null
}

type Better = 'lower' | 'higher' | 'neutral'

/** "44 → 36 min (−8)" with a good/bad tone. */
function Delta({ from, to, fmt, unitDiff, better }: { from: number; to: number; fmt: (n: number) => string; unitDiff: (d: number) => string; better: Better }) {
  const d = to - from
  const same = Math.abs(d) < 0.5
  const tone = same || better === 'neutral' ? '' : (d < 0) === (better === 'lower') ? 'good' : 'bad'
  return (
    <div className={`delta ${tone}`}>
      {fmt(from)} → {fmt(to)} {same ? <span>(same)</span> : <span>({d > 0 ? '+' : '−'}{unitDiff(Math.abs(d))})</span>}
    </div>
  )
}

const mins = (s: number) => `${Math.round(s / 60)} min`
const minsDiff = (s: number) => `${Math.round(s / 60)}`

export function SummaryCards({ summary: s, loading, pinned }: Props) {
  const b = pinned?.summary ?? null
  const served = s ? s.need_bus_total - s.need_bus_unserved : 0
  const servedPct = s && s.need_bus_total > 0 ? served / s.need_bus_total : 1
  return (
    <div className={`cards ${loading ? 'stale' : ''}`}>
      <div className="card hero-card">
        <div className="card-label">Everyone out in</div>
        <div className="card-value">{!s ? '—' : s.people_evacuating > 0 ? fmtDuration(s.sim_clearance_s) : 'No one leaves'}</div>
        {s && b ? (
          <Delta from={b.sim_clearance_s} to={s.sim_clearance_s} fmt={mins} unitDiff={minsDiff} better="lower" />
        ) : (
          <div className="card-sub keep">
            {s && s.people_evacuating > 0 ? `from alert · driving time ${fmtDuration(s.clearance_time_s)}` : 'from alert until the last car is out'}
          </div>
        )}
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot evac" /> Evacuating
        </div>
        <div className="card-value">{s ? fmtCompact(s.people_evacuating) : '—'}</div>
        {s && b ? <Delta from={b.people_evacuating} to={s.people_evacuating} fmt={fmtCompact} unitDiff={fmtCompact} better="neutral" /> : <div className="card-sub">people</div>}
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot shelter" /> Sheltering
        </div>
        <div className="card-value">{s ? fmtCompact(s.people_sheltering) : '—'}</div>
        {s && b ? <Delta from={b.people_sheltering} to={s.people_sheltering} fmt={fmtCompact} unitDiff={fmtCompact} better="neutral" /> : <div className="card-sub">people, in place</div>}
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
        {s && b ? (
          <Delta from={b.need_bus_unserved} to={s.need_bus_unserved} fmt={(n) => `${fmtInt(n)} left`} unitDiff={fmtInt} better="lower" />
        ) : (
          <div className="card-sub">{s ? `${Math.round(servedPct * 100)}% picked up before plume arrives` : ' '}</div>
        )}
      </div>
      <div className="card narrow">
        <div className="card-label">Runtime</div>
        <div className="card-value mono">{s ? `${fmtInt(s.runtime_ms)}` : '—'}<small> ms</small></div>
        <div className="card-sub">{s ? `${s.bottleneck_edge_ids.length} bottleneck${s.bottleneck_edge_ids.length === 1 ? '' : 's'}` : ' '}</div>
      </div>
    </div>
  )
}
