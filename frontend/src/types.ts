// Mirrors contracts/api_response.json and contracts/engine_api.py::ScenarioParams.
import type { Feature, FeatureCollection, LineString, Polygon } from 'geojson'

export type Chemical = 'chlorine' | 'ammonia'
export type SpillSize = 'small' | 'large'
export type TimeOfDay = 'night' | 'day' | 'gameday'
export type Decision = 'evacuate' | 'shelter' | 'outside'

export interface ScenarioParams {
  release_lon: number
  release_lat: number
  chemical: Chemical
  spill_size: SpillSize
  wind_from_deg: number
  wind_speed_mps: number
  time_of_day: TimeOfDay
  compliance: number
  bus_count: number
  bus_capacity: number
  contraflow: boolean
  closed_edge_ids: number[]
}

export interface Summary {
  clearance_time_s: number
  people_evacuating: number
  people_sheltering: number
  need_bus_total: number
  need_bus_unserved: number
  bottleneck_edge_ids: number[]
  runtime_ms: number
}

export interface BlockProps {
  block_id: string
  decision: Decision
  plume_arrival_s: number | null
  est_exit_time_s: number | null
  wave: number | null
  drivers: number
  walkers: number
  need_bus: number
  vulnerability: number
}

export interface EdgeProps {
  edge_id: number
  name: string | null
  flow_veh: number
  peak_load_ratio: number
  congested_at_s: number | null
  is_bottleneck: boolean
}

export interface Bus {
  bus_id: number
  stops: string[]
  arrival_s: number[]
  load: number[]
  path: [number, number][]
}

export type BlockFeature = Feature<Polygon, BlockProps>
export type EdgeFeature = Feature<LineString, EdgeProps>

export interface ScenarioResponse {
  params: ScenarioParams
  summary: Summary
  zones: FeatureCollection<Polygon, { kind: 'isolation' | 'protect' }>
  blocks: FeatureCollection<Polygon, BlockProps>
  edges: FeatureCollection<LineString, EdgeProps>
  buses: Bus[]
  timeline: { step_s: number; edge_load: Record<string, number[]> }
}

export type RailCollection = FeatureCollection<LineString, { rail_id: number; name: string | null }>

export interface Insights {
  source?: string
  n_scenarios?: number
  top_bottlenecks: { edge_id: number; name: string; times_bottleneck: number; share: number }[]
  facilities_in_zone: { facility_id: string; name: string; type: string; share: number }[]
  worst_wind: { wind_from_deg: number; mean_clearance_s: number; mean_unserved: number; n?: number }[]
}

export interface AssumptionItem {
  name: string
  value: string | number | boolean
  unit?: string
  note?: string
}
export interface Assumptions {
  source: string
  groups: { title: string; items: AssumptionItem[] }[]
  data_sources: { name: string; detail: string }[]
  limitations: string[]
}
