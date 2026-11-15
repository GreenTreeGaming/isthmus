import type { BlockProps } from '../types'
import { fmtSpan } from './format'

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
export function explainBlock(p: BlockProps, t: WaveTiming, flood = false): Explanation {
  return flood ? explainFlood(p, t) : explainChemical(p, t)
}

function explainChemical(p: BlockProps, t: WaveTiming): Explanation {
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

/** Flood wording: water instead of gas, hours instead of minutes, upper floor instead of windows shut. */
function explainFlood(p: BlockProps, t: WaveTiming): Explanation {
  const water = p.plume_arrival_s
  const out = p.est_exit_time_s
  const span = (s: number) => fmtSpan(Math.max(0, s))
  if (p.decision === 'shelter') {
    const sentence =
      water != null && out != null
        ? `Water arrives in ${span(water)}, getting out would take ${span(out)}.`
        : water != null
          ? `Water arrives in ${span(water)} — too soon to get out safely.`
          : 'Getting out would take longer than the water needs to arrive.'
    return {
      tone: 'shelter',
      headline: 'Stay and move to an upper floor',
      sentence,
      why: 'Water reaches this block before people could drive out, so they stay and move to an upper floor.',
    }
  }
  if (p.decision === 'evacuate') {
    const w = p.wave ?? 0
    const leave = departureS(w, t)
    const parts = [out != null ? `out by ${span(out)}` : null, water != null ? `water arrives at ${span(water)}` : 'water not expected here'].filter(Boolean)
    const margin = water != null && out != null ? water - out : null
    return {
      tone: 'evacuate',
      headline: `Evacuate in wave ${w + 1} (leave at ${span(leave)})`,
      sentence: parts.join(', ') + '.',
      why:
        margin != null
          ? `There is ${span(margin)} to spare between getting out and the water arriving. People drive toward higher ground; waves stagger departures so the roads don't jam.`
          : "People drive toward higher ground; waves stagger departures so the roads don't jam.",
    }
  }
  return {
    tone: 'outside',
    headline: 'Outside the flood zone',
    sentence: 'No action needed for this area.',
    why: 'At this lake level the rising water does not reach this block.',
  }
}
