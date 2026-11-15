import type { FloodSource, ScenarioParams, ScenarioResponse, ZoneFeature } from '../types'

type Zones = ScenarioResponse['zones']

/** Controls / request params: is this a flood scenario? (Missing hazard = chemical.) */
export const isFloodParams = (p: Partial<ScenarioParams> | null | undefined) => p?.hazard === 'flood'

/** A result is a flood if the backend says so, or (older echo) its zones are flood zones. */
export function isFloodResult(r: ScenarioResponse | null | undefined): boolean {
  if (!r) return false
  return r.params?.hazard === 'flood' || r.zones.features.some((f) => f.properties.kind.startsWith('flood'))
}

/** The substance that arrives: used in every "X arrives" sentence. */
export const hazardWord = (flood: boolean) => (flood ? 'water' : 'gas')

export const SOURCE_SHORT: Record<FloodSource, string> = { mendota: 'Lake Mendota', monona: 'Monona + Yahara', both: 'Both lakes' }
/** Sentence subject: "Both lakes rise 1.5 m…" */
export const SOURCE_SENTENCE: Record<FloodSource, string> = {
  mendota: 'Lake Mendota rises',
  monona: 'Lake Monona and the Yahara River rise',
  both: 'Both lakes rise',
}

export const fmtRise = (m: number) => `+${Number(m.toFixed(2))} m`

export function floodSteps(z: Zones | null | undefined): ZoneFeature[] {
  if (!z) return []
  return z.features.filter((f) => f.properties.kind === 'flood_step').sort((a, b) => (a.properties.t_s ?? 0) - (b.properties.t_s ?? 0))
}

/** The water extent at time t: the last flood_step with t_s <= t (null before the first one). */
export function floodStepAt(steps: ZoneFeature[], t: number): ZoneFeature | null {
  let cur: ZoneFeature | null = null
  for (const f of steps) {
    if ((f.properties.t_s ?? 0) <= t) cur = f
    else break
  }
  return cur
}

/** Peak time of the water (last flood step), seconds; 0 for a chemical result. */
export function floodPeakS(r: ScenarioResponse): number {
  const steps = floodSteps(r.zones)
  const last = steps.at(-1)?.properties.t_s
  if (last != null) return last
  return isFloodResult(r) && r.params.flood_peak_h ? r.params.flood_peak_h * 3600 : 0
}
