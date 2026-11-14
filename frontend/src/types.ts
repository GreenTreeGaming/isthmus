// Mirrors contracts/api_response.json and contracts/engine_api.py::ScenarioParams.
import type { Feature, FeatureCollection, LineString, MultiPolygon, Polygon } from 'geojson'

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
  sim_clearance_s: number // alert -> last car out (traffic sim, incl. mobilization + waves)
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

export type BlockFeature = Feature<Polygon | MultiPolygon, BlockProps>
/** Static outlines from GET /blocks (fetched once). */
export type BlockGeoCollection = FeatureCollection<Polygon | MultiPolygon, { block_id: string }>
export interface BlockFrequency {
  block_id: string
  share_shelter: number
  share_evacuate: number
}
export type EdgeFeature = Feature<LineString, EdgeProps>

export interface ScenarioResponse {
  params: ScenarioParams
  summary: Summary
  zones: FeatureCollection<Polygon, { kind: 'isolation' | 'protect' }>
  blocks: Record<string, Omit<BlockProps, 'block_id'>> // geometry comes from GET /blocks
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
  by_time_of_day?: {
    time_of_day: string
    mean_clearance_s: number
    mean_evacuating: number
    mean_sheltering: number
    mean_unserved?: number
  }[]
  n_failed?: number
  median_runtime_ms?: number | null
}

export interface AssumptionItem {
  name: string
  value: string | number | boolean
  unit?: string | null
  note?: string | null
  key?: string
}
export interface Assumptions {
  source: string
  groups: { title: string; items: AssumptionItem[] }[]
  data_sources: { name: string; detail: string }[]
  limitations: string[]
}
