import type { BlockFeature, BlockGeoCollection, Bus, BlockProps, ScenarioResponse } from '../types'
import { along, centroid } from './geo'

export interface BlockPoint {
  position: [number, number]
  props: BlockProps
}

export interface BusStop {
  bus_id: number
  stop_id: string
  index: number
  kind: 'garage' | 'pickup' | 'shelter'
  position: [number, number] | null // null = stop location unknown (no marker)
  arrival_s: number
  load: number
  deadline_s: number | null
  late: boolean
}

export interface Derived {
  blockFeatures: BlockFeature[] // static geometry (GET /blocks) joined with this run's properties
  blockPoints: BlockPoint[]
  stops: BusStop[]
  busLate: Map<number, number> // bus_id -> number of late pickups
  duration_s: number
  step_s: number
  nSteps: number
}

/** Stop coordinates are only known when the path has exactly one vertex per stop (contract example + mock). */
export const stopsLocatable = (b: Bus) => b.path.length === b.stops.length && b.path.length > 0

function stopKind(id: string, i: number, n: number): BusStop['kind'] {
  if (id.startsWith('garage') || id.startsWith('depot')) return 'garage'
  if (id.startsWith('shelter')) return 'shelter'
  if (id.startsWith('stop')) return 'pickup'
  return i === 0 ? 'garage' : i === n - 1 ? 'shelter' : 'pickup'
}

function stopPosition(b: Bus, i: number): [number, number] | null {
  const c = b.stop_coords?.[i]
  if (c) return [c[0], c[1]]
  return stopsLocatable(b) ? [b.path[i][0], b.path[i][1]] : null
}

export function outerRing(f: BlockGeoCollection['features'][number]) {
  return f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0]
}

export function derive(r: ScenarioResponse, geo: BlockGeoCollection): Derived {
  const blockFeatures: BlockFeature[] = []
  const blockPoints: BlockPoint[] = []
  for (const f of geo.features) {
    const run = r.blocks[f.properties.block_id]
    if (!run) continue
    const props: BlockProps = { ...run, block_id: f.properties.block_id }
    blockFeatures.push({ type: 'Feature', geometry: f.geometry, properties: props })
    blockPoints.push({ position: centroid(outerRing(f)), props })
  }

  const stops: BusStop[] = []
  const busLate = new Map<number, number>()
  for (const b of r.buses) {
    b.stops.forEach((id, i) => {
      const kind = stopKind(id, i, b.stops.length)
      const pos = stopPosition(b, i)
      // The exact deadline the engine's bus router enforced; scheduled stops always meet it.
      const deadline = kind === 'pickup' ? (b.deadline_s?.[i] ?? null) : null
      const late = deadline != null && b.arrival_s[i] > deadline
      if (late) busLate.set(b.bus_id, (busLate.get(b.bus_id) ?? 0) + 1)
      stops.push({ bus_id: b.bus_id, stop_id: id, index: i, kind, position: pos, arrival_s: b.arrival_s[i], load: b.load[i], deadline_s: deadline, late })
    })
  }

  const step_s = r.timeline.step_s || 30
  const nSteps = Math.max(0, ...Object.values(r.timeline.edge_load).map((a) => a.length))
  const lastBus = Math.max(0, ...r.buses.map((b) => b.arrival_s.at(-1) ?? 0))
  const duration_s = Math.max(nSteps * step_s, r.summary.clearance_time_s ?? 0, r.summary.sim_clearance_s ?? 0, lastBus, 600)
  return { blockFeatures, blockPoints, stops, busLate, duration_s, step_s, nSteps }
}

/** Interpolated load ratio of an edge at time t (seconds). */
export function loadAt(series: number[] | undefined, t: number, step: number): number | null {
  if (!series || series.length === 0) return null
  const x = t / step
  const i = Math.floor(x)
  if (i >= series.length - 1) return series[series.length - 1]
  if (i < 0) return series[0]
  return series[i] + (series[i + 1] - series[i]) * (x - i)
}

/** Where a bus is at time t. */
export function busPosition(b: Bus, t: number): [number, number] | null {
  if (b.path.length === 0) return null
  const arr = b.arrival_s
  const end = arr.at(-1) ?? 0
  if (t >= end) return [b.path.at(-1)![0], b.path.at(-1)![1]]
  if (stopsLocatable(b)) {
    for (let i = 0; i < arr.length - 1; i++) {
      if (t <= arr[i + 1]) {
        const span = arr[i + 1] - arr[i] || 1
        return along([b.path[i], b.path[i + 1]], (t - arr[i]) / span)
      }
    }
  }
  return along(b.path, end ? t / end : 1)
}
