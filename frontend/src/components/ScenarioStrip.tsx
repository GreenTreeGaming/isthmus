import type { ScenarioParams } from '../types'
import { compass } from '../lib/format'

interface Props {
  params: ScenarioParams
  railName: string | null
  place: string
  children?: React.ReactNode
}

const CHEM: Record<string, string> = { chlorine: 'Chlorine', ammonia: 'Ammonia' }
const TOD: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }

export function ScenarioStrip({ params: p, railName, place, children }: Props) {
  const parts = [
    CHEM[p.chemical] ?? p.chemical,
    `${p.spill_size === 'large' ? 'Large' : 'Small'} spill`,
    TOD[p.time_of_day] ?? p.time_of_day,
    `Wind ${compass(p.wind_from_deg)} ${p.wind_speed_mps.toFixed(1)} m/s`,
    `${p.bus_count} bus${p.bus_count === 1 ? '' : 'es'}`,
    p.contraflow ? 'Contraflow on' : null,
    p.compliance < 0.995 ? `${Math.round(p.compliance * 100)}% comply` : null,
  ].filter(Boolean)
  return (
    <div className="scenario-strip">
      <span className="strip-pin" aria-hidden />
      <div className="strip-where">
        <b>{railName ?? 'Rail line'}</b>
        <span>{place}</span>
      </div>
      <div className="strip-params">
        {parts.map((t, i) => (
          <span key={i}>{t}</span>
        ))}
      </div>
      {children && <div className="strip-actions">{children}</div>}
    </div>
  )
}
