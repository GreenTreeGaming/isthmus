import type { ScenarioParams } from '../types'
import { compass } from '../lib/format'

interface Props {
  params: ScenarioParams
  railName: string | null
  place?: string
  children?: React.ReactNode
}

const CHEM: Record<string, string> = { chlorine: 'Chlorine', ammonia: 'Ammonia' }
const TOD: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }

export function ScenarioStrip({ params: p, railName, children }: Props) {
  const parts = [
    CHEM[p.chemical] ?? p.chemical,
    `${p.spill_size === 'large' ? 'Large' : 'Small'} spill`,
    TOD[p.time_of_day] ?? p.time_of_day,
    `Wind ${compass(p.wind_from_deg)} ${p.wind_speed_mps.toFixed(1)} m/s`,
    `${p.bus_count} bus${p.bus_count === 1 ? '' : 'es'}`,
    p.contraflow ? 'Contraflow on' : null,
    Math.abs(p.compliance - 0.85) > 0.005 ? `${Math.round(p.compliance * 100)}% comply` : null,
  ].filter(Boolean)
  return (
    <div className="hud-scenario">
      <span className="strip-pin" aria-hidden />
      <div className="hud-where">
        <b title={railName ?? undefined}>{railName ?? 'Rail line'}</b>
        <span className="hud-params" title={parts.join(' · ')}>{parts.join(' · ')}</span>
      </div>
      {children}
    </div>
  )
}
