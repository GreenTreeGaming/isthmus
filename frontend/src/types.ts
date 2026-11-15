// Mirrors contracts/api_response.json and contracts/engine_api.py::ScenarioParams.
import type { Feature, FeatureCollection, LineString, MultiPolygon, Polygon } from 'geojson'

export type Chemical = 'chlorine' | 'ammonia'
export type SpillSize = 'small' | 'large'
export type TimeOfDay = 'night' | 'day' | 'gameday'
export type Decision = 'evacuate' | 'shelter' | 'outside'
export type HazardType = 'chemical' | 'flood'
/** Which lake rises: Mendota, Monona (plus the Yahara River below it), or both. */
export type FloodSource = 'mendota' | 'monona' | 'both'

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
  /** "chemical" uses release point, chemical, spill and wind; "flood" uses the flood_* fields below. */
  hazard: HazardType
  flood_source: FloodSource
  /** Lake rise above normal at the peak, meters (backend: 0 < x <= 5). */
  flood_rise_m: number
  /** Hours from the alert until the water peaks (backend: 0 < x <= 72). */
  flood_peak_h: number
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
  /** When the hazard arrives: gas, or (flood) the rising water. */
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
  /** Backend extra (not yet in contracts/): OSM road class, e.g. primary, residential. */
  road_class?: string | null
}

export interface Bus {
  bus_id: number
  stops: string[]
  arrival_s: number[]
  load: number[]
  path: [number, number][]
  /** Per stop: the hazard-arrival deadline (gas or water) the bus router enforced (null for garage/shelter). */
  deadline_s?: (number | null)[]
  /** Backend extra (not yet in contracts/): one [lon, lat] per stop, null where unknown. */
  stop_coords?: ([number, number] | null)[]
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

/**
 * Chemical: 'isolation' + 'protect'. Flood: 'flood' (all land flooded at the peak), 'flood_source' (the rising lakes)
 * and several 'flood_step' features with { t_s, rise_m } (cumulative flooded land at t_s after the alert).
 */
export type ZoneKind = 'isolation' | 'protect' | 'flood' | 'flood_source' | 'flood_step'
export interface ZoneProps {
  kind: ZoneKind
  t_s?: number
  rise_m?: number
}
export type ZoneFeature = Feature<Polygon | MultiPolygon, ZoneProps>

export interface ScenarioResponse {
  /** Older backends may not echo the hazard fields. */
  params: Omit<ScenarioParams, 'hazard' | 'flood_source' | 'flood_rise_m' | 'flood_peak_h'> & Partial<ScenarioParams>
  summary: Summary
  zones: FeatureCollection<Polygon | MultiPolygon, ZoneProps>
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
  by_wind_speed?: { wind_speed_mps: number; mean_clearance_s: number; mean_evacuating: number; mean_sheltering: number }[]
  garage_in_zone_share?: number
  bottleneck_method?: string
  /** Flood batch results; absent until the flood batch has run. */
  flood?: FloodInsights
}

export interface FloodInsights {
  n_scenarios: number
  by_rise: {
    rise_m: number
    flooded_km2: number
    mean_people_evacuating: number
    mean_people_sheltering: number
    mean_clearance_s: number
    mean_need_bus: number
    mean_unserved: number
  }[]
  /** How far the lakes must rise before each place / road goes underwater (ascending). */
  facilities: { name: string; type: string; flood_rise_m: number }[]
  roads: { name: string; flood_rise_m: number }[]
  garage_flood_rise_m?: number | null
}

export interface RobustnessVariant {
  n: number
  failed: number
  clearance_min_by_wind_speed: Record<string, number>
  mean_clearance_min: number
  mean_evacuating: number
  mean_unserved: number
  capitol_lakes_in_zone: number
  garage_in_zone: number
  top_choke_points: string[]
}
export interface Robustness {
  grid: { n_scenarios: number; n_points: number; times: string[]; wind_speeds: number[] }
  variants: Record<string, RobustnessVariant>
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
