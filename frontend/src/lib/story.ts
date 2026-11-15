import type { ScenarioResponse } from '../types'
import { fmtInt } from './format'

const CHEM: Record<string, string> = { chlorine: 'chlorine', ammonia: 'ammonia' }

/** One plain-English sentence summarizing the current plan (area-level, never individuals). */
export function planStory(r: ScenarioResponse, railName: string | null): string {
  const s = r.summary
  const p = r.params
  const waves = new Set(Object.values(r.blocks).filter((b) => b.decision === 'evacuate').map((b) => b.wave ?? 0)).size
  const where = railName ? ` on the ${railName}` : ''
  const parts: string[] = [`A ${p.spill_size} ${CHEM[p.chemical] ?? p.chemical} spill${where}:`]
  if (s.people_evacuating > 0)
    parts.push(`${fmtInt(s.people_evacuating)} people leave in ${waves} wave${waves === 1 ? '' : 's'}`)
  else parts.push('nobody can get out ahead of the gas')
  parts[parts.length - 1] += s.people_sheltering > 0 ? ` and ${fmtInt(s.people_sheltering)} stay indoors, because the gas would reach them first.` : '.'
  if (s.need_bus_total > 0)
    parts.push(
      s.need_bus_unserved > 0
        ? `${fmtInt(s.need_bus_unserved)} of ${fmtInt(s.need_bus_total)} residents who need a ride can't be reached before the gas.`
        : `All ${fmtInt(s.need_bus_total)} residents who need a ride get a bus pickup before the gas arrives.`,
    )
  if (s.people_evacuating > 0) parts.push(`The last car is out ${Math.round(s.sim_clearance_s / 60)} min after the alert.`)
  return parts.join(' ')
}
