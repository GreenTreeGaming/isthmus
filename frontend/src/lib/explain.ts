import type { BlockProps } from '../types'

/** Wave departure timing, read from engine/assumptions.py via GET /assumptions (defaults match it). */
export interface WaveTiming {
  mobilization_s: number
  wave_interval_s: number
}
export const DEFAULT_TIMING: WaveTiming = { mobilization_s: 300, wave_interval_s: 600 }

export const departureS = (wave: number, t: WaveTiming) => t.mobilization_s + wave * t.wave_interval_s

const min = (s: number) => `${Math.max(0, Math.round(s / 60))} min`

export interface Explanation {
  tone: 'shelter' | 'evacuate' | 'outside'
  headline: string
  sentence: string
  why: string
}

/** Plain-English reason for a block's decision. Area-level: describes the block, never a person. */
export function explainBlock(p: BlockProps, t: WaveTiming): Explanation {
  const gas = p.plume_arrival_s
  const out = p.est_exit_time_s
  if (p.decision === 'shelter') {
    const sentence =
      gas != null && out != null
        ? `Gas arrives in ${min(gas)}, getting out would take ${min(out)}.`
        : gas != null
          ? `Gas arrives in ${min(gas)} — too soon to get out safely.`
          : 'Getting out would take longer than the gas needs to arrive.'
    return {
      tone: 'shelter',
      headline: 'Shelter in place',
      sentence,
      why: 'People would still be on the road when the gas arrived, so staying indoors with windows and vents shut is safer.',
    }
  }
  if (p.decision === 'evacuate') {
    const w = p.wave ?? 0
    const leave = departureS(w, t)
    const parts = [out != null ? `out by ${min(out)}` : null, gas != null ? `gas arrives at ${min(gas)}` : 'gas not expected here'].filter(Boolean)
    const margin = gas != null && out != null ? gas - out : null
    return {
      tone: 'evacuate',
      headline: `Evacuate in wave ${w + 1} (leave at ${min(leave)})`,
      sentence: parts.join(', ') + '.',
      why:
        margin != null
          ? `There is ${min(margin)} to spare between getting out and the gas arriving. Waves stagger departures so the roads don't jam.`
          : "Waves stagger departures so the roads don't jam.",
    }
  }
  return {
    tone: 'outside',
    headline: 'Outside the danger zone',
    sentence: 'No action needed for this area.',
    why: 'The ERG protective-action zone does not reach this block for this scenario.',
  }
}
