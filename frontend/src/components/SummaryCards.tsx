import type { Summary } from '../types'
import { fmtCompact, fmtDuration, fmtInt } from '../lib/format'
import { useTween } from '../lib/useTween'

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

/** A number that animates between values. */
function Num({ value, fmt }: { value: number | null | undefined; fmt: (n: number) => string }) {
  const v = useTween(value ?? null)
  return <>{v == null ? '—' : fmt(v)}</>
}

const mins = (s: number) => `${Math.round(s / 60)} min`
const minsDiff = (s: number) => `${Math.round(s / 60)}`

function Skeleton() {
  return (
    <div className="cards skeleton" aria-busy="true" aria-label="Running the first scenario">
      {['hero-card', '', '', 'wide', 'narrow'].map((c, i) => (
        <div key={i} className={`card ${c}`}>
          <div className="sk sk-label" />
          <div className="sk sk-value" />
          <div className="sk sk-sub" />
        </div>
      ))}
    </div>
  )
}

export function SummaryCards({ summary: s, loading, pinned }: Props) {
  if (!s) return <Skeleton />
  const b = pinned?.summary ?? null
  const served = s.need_bus_total - s.need_bus_unserved
  const servedPct = s.need_bus_total > 0 ? served / s.need_bus_total : 1
  const unserved = s.need_bus_unserved > 0
  return (
    <div className={`cards ${loading ? 'stale' : ''}`}>
      <div className="card hero-card">
        <div className="card-label">Everyone out in</div>
        <div className="card-value">{s.people_evacuating > 0 ? <Num value={s.sim_clearance_s} fmt={fmtDuration} /> : 'No one leaves'}</div>
        <div className="card-sub">From the alert until the last evacuating car is out</div>
        {b && <Delta from={b.sim_clearance_s} to={s.sim_clearance_s} fmt={mins} unitDiff={minsDiff} better="lower" />}
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot evac" /> Evacuating
        </div>
        <div className="card-value"><Num value={s.people_evacuating} fmt={fmtCompact} /></div>
        <div className="card-sub">People told to leave, in timed waves</div>
        {b && <Delta from={b.people_evacuating} to={s.people_evacuating} fmt={fmtCompact} unitDiff={fmtCompact} better="neutral" />}
      </div>
      <div className="card">
        <div className="card-label">
          <i className="dot shelter" /> Sheltering
        </div>
        <div className="card-value"><Num value={s.people_sheltering} fmt={fmtCompact} /></div>
        <div className="card-sub">People told to stay indoors, windows shut</div>
        {b && <Delta from={b.people_sheltering} to={s.people_sheltering} fmt={fmtCompact} unitDiff={fmtCompact} better="neutral" />}
      </div>
      <div className={`card wide ${unserved ? 'danger' : ''}`}>
        <div className="card-label">
          <i className="dot bus" /> Need a bus
        </div>
        <div className="card-value">
          <Num value={s.need_bus_total} fmt={fmtInt} />
          {unserved && <span className="bad small"> · <Num value={s.need_bus_unserved} fmt={fmtInt} /> left behind</span>}
        </div>
        <div className="meter" aria-label={`${Math.round(servedPct * 100)}% picked up before the gas arrives`}>
          <span style={{ width: `${servedPct * 100}%` }} />
        </div>
        <div className="card-sub">
          {unserved
            ? `${fmtInt(s.need_bus_unserved)} not picked up before the gas arrives`
            : s.need_bus_total > 0
              ? 'Residents without a car — all picked up before the gas'
              : 'No one in the zone needs a ride'}
        </div>
        {b && <Delta from={b.need_bus_unserved} to={s.need_bus_unserved} fmt={(n) => `${fmtInt(n)} left`} unitDiff={fmtInt} better="lower" />}
      </div>
      <div className="card narrow">
        <div className="card-label">Runtime</div>
        <div className="card-value mono"><Num value={s.runtime_ms} fmt={fmtInt} /><small> ms</small></div>
        <div className="card-sub">To simulate this scenario</div>
      </div>
    </div>
  )
}
