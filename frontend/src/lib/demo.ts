import type { ScenarioParams, Summary } from '../types'
import { fmtInt } from './format'

export interface DemoStep {
  title: string
  /** Shown while the step is still running. */
  caption: string
  /** Caption with the live numbers once the run (and its baseline, if any) is back. */
  live?: (s: Summary, base: Summary | null) => string
  /** What to try on the map during this step. */
  try?: string
  /** Overrides on top of DEFAULT_PARAMS (the release point is always the Capitol, snapped to rail). */
  params: Partial<ScenarioParams>
  /** Scenario the deltas are measured against (run silently and pinned). Omit for no comparison. */
  compareTo?: Partial<ScenarioParams>
  compareLabel?: string
}

/** Wisconsin State Capitol — the demo derailment is placed on the nearest rail line to it. */
export const CAPITOL: [number, number] = [-89.3841, 43.0747]

const BASE: Partial<ScenarioParams> = {
  chemical: 'chlorine',
  spill_size: 'large',
  wind_from_deg: 225,
  wind_speed_mps: 1.5,
  time_of_day: 'day',
  bus_count: 20,
  contraflow: false,
}

// Each step was checked against the real engine on the Madison silver data so the effect is visible.
const n = (x: number) => fmtInt(x)

export const DEMO_STEPS: DemoStep[] = [
  {
    title: 'Who leaves, who stays',
    caption:
      'A chlorine tank car derails near the Capitol. Orange areas evacuate in timed waves; purple areas shelter in place because the gas would reach them before they could get out.',
    live: (s) =>
      `A chlorine tank car derails near the Capitol. ${n(s.people_evacuating)} people in the orange areas leave in timed waves, earliest gas first. ${n(s.people_sheltering)} in the purple areas are told to stay indoors: the gas would reach them before they could drive out.`,
    try: 'Click a purple or orange block to see its reason.',
    params: { ...BASE },
  },
  {
    title: 'Faster wind',
    caption: 'The wind picks up to 4 m/s. The danger zone shrinks, but the gas arrives sooner, so more areas must shelter instead of driving out.',
    live: (s, b) =>
      `The wind picks up to 4 m/s. The danger zone gets smaller, yet only ${n(s.people_evacuating)} people can leave${b ? `, down from ${n(b.people_evacuating)}` : ''}: the gas now arrives before most blocks could get out, so driving out is more dangerous than sheltering.`,
    try: 'Press Play on the timeline to watch the traffic.',
    params: { ...BASE, wind_speed_mps: 4 },
    compareTo: { ...BASE },
    compareLabel: 'Wind 1.5 m/s',
  },
  {
    title: 'Game day',
    caption: 'Wind from the east carries the gas toward Camp Randall. On a game day about 75,000 extra people are nearby.',
    live: (s, b) =>
      `Wind from the east carries the gas toward Camp Randall. On game day the stadium crowd adds to everyone else: ${n(s.people_sheltering)} people must shelter in place${b ? `, compared with ${n(b.people_sheltering)} on a normal day` : ''}.`,
    try: 'The cards show the change from a normal day with the same wind.',
    params: { ...BASE, wind_from_deg: 90, time_of_day: 'gameday' },
    compareTo: { ...BASE, wind_from_deg: 90 },
    compareLabel: 'Same wind, normal day',
  },
  {
    title: 'Too few buses',
    caption: 'At night, with only 5 buses instead of 20, residents who need a ride cannot all be reached before the gas arrives.',
    live: (s, b) =>
      s.need_bus_unserved > 0
        ? `Night, and only 5 buses instead of 20. Of ${n(s.need_bus_total)} residents who need a ride, ${n(s.need_bus_unserved)} can't be reached before the gas arrives${b ? ` (with 20 buses: ${n(b.need_bus_unserved)})` : ''}. They are in the areas with the most residents who need help.`
        : `Night, and only 5 buses instead of 20. Here all ${n(s.need_bus_total)} residents who need a ride are still reached in time; try fewer buses on the left.`,
    try: 'Click a blue bus route to see each pickup time against its gas deadline.',
    params: { ...BASE, time_of_day: 'night', bus_count: 5 },
    compareTo: { ...BASE, time_of_day: 'night' },
    compareLabel: 'Night, 20 buses',
  },
]
