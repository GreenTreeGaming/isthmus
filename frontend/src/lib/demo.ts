import type { ScenarioParams } from '../types'

export interface DemoStep {
  title: string
  caption: string
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
export const DEMO_STEPS: DemoStep[] = [
  {
    title: 'Who leaves, who stays',
    caption:
      'A chlorine tank car derails near the Capitol. Orange areas evacuate in timed waves; purple areas shelter in place because the gas would reach them before they could get out.',
    params: { ...BASE },
  },
  {
    title: 'Faster wind',
    caption:
      'At 4 m/s the gas arrives sooner. For more areas, driving out is now more dangerous than sheltering indoors — so more people are told to stay put.',
    params: { ...BASE, wind_speed_mps: 4 },
    compareTo: { ...BASE },
    compareLabel: 'Wind 1.5 m/s',
  },
  {
    title: 'Game day',
    caption:
      'Wind from the east carries the gas toward Camp Randall. On a game day about 75,000 extra people are nearby, and almost all of them have to shelter in place.',
    params: { ...BASE, wind_from_deg: 90, time_of_day: 'gameday' },
    compareTo: { ...BASE, wind_from_deg: 90 },
    compareLabel: 'Same wind, normal day',
  },
  {
    title: 'Too few buses',
    caption:
      'Cut the fleet from 20 buses to 2. Residents who need a ride are no longer all picked up before the gas arrives — the areas with the most residents who need help are left waiting.',
    params: { ...BASE, bus_count: 2 },
    compareTo: { ...BASE },
    compareLabel: '20 buses',
  },
]
