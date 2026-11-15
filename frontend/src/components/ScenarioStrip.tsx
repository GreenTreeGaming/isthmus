import type { ScenarioParams } from '../types'
import { compass } from '../lib/format'
import { SOURCE_SHORT, fmtRise } from '../lib/hazard'

interface Props {
  params: ScenarioParams
  railName: string | null
  place?: string
  children?: React.ReactNode
}

const CHEM: Record<string, string> = { chlorine: 'Chlorine', ammonia: 'Ammonia' }
const TOD: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }

export function ScenarioStrip({ params: p, railName, children }: Props) {
  const flood = p.hazard === 'flood'
  const title = flood ? `Flood · ${SOURCE_SHORT[p.flood_source]} ${fmtRise(p.flood_rise_m)}` : railName ?? 'Rail line'
  const parts = flood ? [
    `Peak in ${p.flood_peak_h} h`,
    TOD[p.time_of_day] ?? p.time_of_day,
    `${p.bus_count} bus${p.bus_count === 1 ? '' : 'es'}`,
    p.contraflow ? 'Contraflow on' : null,
    Math.abs(p.compliance - 0.85) > 0.005 ? `${Math.round(p.compliance * 100)}% comply` : null,
  ].filter(Boolean) : [
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
      <span className={`strip-pin ${flood ? 'water' : ''}`} aria-hidden />
      <div className="hud-where">
        <b title={title}>{title}</b>
        <span className="hud-params" title={parts.join(' · ')}>{parts.join(' · ')}</span>
      </div>
      {children}
    </div>
  )
}
