import { useEffect, useMemo, useRef, useState } from 'react'
import DeckGL, { type DeckGLRef } from '@deck.gl/react'
import { FlyToInterpolator, WebMercatorViewport, type PickingInfo } from '@deck.gl/core'
import { GeoJsonLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { PathStyleExtension, type PathStyleExtensionProps } from '@deck.gl/extensions'
import { Map } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import '../lib/maplibreWorker'
import type { FeatureCollection, Polygon, Position } from 'geojson'
import type { BlockFeature, BlockFrequency, BlockGeoCollection, Bus, EdgeFeature, RailCollection, ScenarioParams, ScenarioResponse, ZoneFeature } from '../types'
import { COLORS, blockColor, frequencyColor, loadColor } from '../lib/colors'
import { busPosition, loadAt, type BusStop, type Derived } from '../lib/derive'
import { fmtDuration } from '../lib/format'
import { along, centroid, distM } from '../lib/geo'
import { floodStepAt, isFloodResult } from '../lib/hazard'
import { Tooltip, type HoverInfo } from './Tooltip'
import type { Selection } from './InfoCard'

const INITIAL_VIEW = { longitude: -89.374, latitude: 43.075, zoom: 13.5, pitch: 0, bearing: 0 }
const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const MAX_PARTICLES = 4000
const ROAD_WEIGHT: Record<string, number> = {
  motorway: 1.6, trunk: 1.6, primary: 1.5, secondary: 1.35, tertiary: 1.2,
  motorway_link: 1.2, trunk_link: 1.2, primary_link: 1.2, secondary_link: 1.1, tertiary_link: 1.05,
  residential: 1, unclassified: 1, living_street: 0.8, service: 0.8,
}

export interface LayerToggles {
  blocks: boolean
  heatmap: boolean
  roads: boolean
  traffic: boolean
  buses: boolean
  frequency: boolean
}

interface Props {
  result: ScenarioResponse | null
  derived: Derived | null
  rail: RailCollection | null
  params: ScenarioParams
  toggles: LayerToggles
  time: number | null // null = peak view
  onPickRelease: (lon: number, lat: number) => void
  hoveredBus: number | null
  setHoveredBus: (id: number | null) => void
  blockGeo: BlockGeoCollection | null
  frequency: Map<string, BlockFrequency> | null
  frequencyMax: number
  selection: Selection | null
  onSelect: (s: Selection | null) => void
  /** When this changes the camera flies to fit these zones (used by the guided demo). */
  fitTo: ScenarioResponse['zones'] | null
  /** Only a click on the rail line itself moves the derailment (used in the demo, so stray clicks don't). */
  railOnly: boolean
}

type Zones = ScenarioResponse['zones']
const WORLD: [number, number][] = [[-180, -85], [180, -85], [180, 85], [-180, 85]]

/** Outer and inner rings of a Polygon or MultiPolygon. */
function rings(f: ZoneFeature): Position[][] {
  return f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat()
}

function ringsBBox(rs: Position[][]): [[number, number], [number, number]] | null {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const ring of rs) for (const [x, y] of ring) {
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y)
  }
  return isFinite(x0) ? [[x0, y0], [x1, y1]] : null
}

// Fit to the danger area only: a flood's rising lake (Mendota is ~10 km across) would zoom the map far out.
const FIT_KINDS = new Set(['isolation', 'protect', 'flood'])
function zonesBBox(z: Zones): [[number, number], [number, number]] | null {
  return ringsBBox(z.features.filter((f) => FIT_KINDS.has(f.properties.kind)).flatMap(rings))
}

/** Zones split by role, cached per response so layers keep stable data (the map re-renders every frame). */
interface SplitZones {
  chem: Zones // isolation + protect (chemical)
  source: ZoneFeature[] // rising lake(s)
  peak: ZoneFeature[] // all land flooded at the peak
  steps: ZoneFeature[] // flooded land over time, ascending t_s
  labels: { position: [number, number]; text: string }[]
}
const splitCache = new WeakMap<Zones, SplitZones>()
function splitZones(z: Zones): SplitZones {
  const hit = splitCache.get(z)
  if (hit) return hit
  const of = (k: string) => z.features.filter((f) => f.properties.kind === k)
  const source = of('flood_source')
  const out: SplitZones = {
    chem: { ...z, features: z.features.filter((f) => f.properties.kind === 'isolation' || f.properties.kind === 'protect') },
    source,
    peak: of('flood'),
    steps: of('flood_step').sort((a, b) => (a.properties.t_s ?? 0) - (b.properties.t_s ?? 0)),
    labels: lakeLabels(source),
  }
  splitCache.set(z, out)
  return out
}

/** "Lake Mendota rising" / "Lake Monona rising": one label per lake, on its largest part. Mendota lies north of the isthmus. */
function lakeLabels(source: ZoneFeature[]) {
  const best = new globalThis.Map<string, { position: [number, number]; size: number }>()
  for (const f of source) {
    const parts = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
    for (const poly of parts) {
      const bb = ringsBBox([poly[0]])
      if (!bb) continue
      const size = distM(bb[0], bb[1])
      if (size < 1500) continue // skip river slivers and small bays
      const position = centroid(poly[0])
      const name = position[1] > 43.085 ? 'Lake Mendota' : 'Lake Monona'
      if ((best.get(name)?.size ?? 0) < size) best.set(name, { position, size })
    }
  }
  return [...best].map(([name, b]) => ({ position: b.position, text: `${name} rising` }))
}

function fitView(z: Zones | null) {
  const bb = z && zonesBBox(z)
  if (!bb) return INITIAL_VIEW
  const width = window.innerWidth
  const height = Math.max(300, window.innerHeight) // the map is full-bleed under the header
  const panel = width > 1700 ? 330 : width > 1280 ? 300 : 272
  try {
    const v = new WebMercatorViewport({ width, height }).fitBounds(bb, {
      padding: { left: panel + 40, right: Math.min(280, width * 0.2), top: Math.min(170, height * 0.26), bottom: Math.min(190, height * 0.27) },
      maxZoom: 15,
    })
    return { longitude: v.longitude, latitude: v.latitude, zoom: v.zoom, pitch: 0, bearing: 0, transitionDuration: 1400, transitionInterpolator: new FlyToInterpolator() }
  } catch {
    return INITIAL_VIEW
  }
}

/** Dim everything outside the protective-action zone so the affected area stands out. */
function dimOutside(z: Zones | null): FeatureCollection<Polygon> | null {
  const protect = z?.features.find((f) => f.properties.kind === 'protect')
  if (!protect) return null
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [WORLD, rings(protect)[0]] } }] }
}

interface Particle {
  path: [number, number][]
  lengthM: number
  edge: EdgeFeature
}

export function MapView({ result, derived, rail, params, toggles, time, onPickRelease, hoveredBus: hoverBus, setHoveredBus, blockGeo, frequency, frequencyMax, selection, onSelect, fitTo, railOnly }: Props) {
  const initialViewState = useMemo(() => fitView(fitTo), [fitTo])
  // A clicked bus stays highlighted like a hovered one.
  const hoveredBus = hoverBus ?? (selection?.kind === 'bus' ? selection.id : null)
  const selectedBlock = selection?.kind === 'block' ? selection.id : null
  const [hover, setHover] = useState<HoverInfo | null>(null)
  const [phase, setPhase] = useState(0)
  const raf = useRef(0)

  // Continuous animation clock for traffic particles and the release pulse.
  useEffect(() => {
    const start = performance.now()
    const tick = (now: number) => {
      setPhase((now - start) / 1000)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [])

  // Crossfade the hazard zones when they change (e.g. the wind turns) instead of snapping.
  const zonesNow = result?.zones ?? null
  const [zoneHist, setZoneHist] = useState<{ cur: Zones | null; prev: Zones | null; at: number }>({ cur: zonesNow, prev: null, at: 0 })
  if (zonesNow !== zoneHist.cur) setZoneHist({ cur: zonesNow, prev: zoneHist.cur, at: phase })
  const zoneFade = Math.min(1, Math.max(0, (phase - zoneHist.at) / 0.8))
  const dim = useMemo(() => dimOutside(zonesNow), [zonesNow])

  // Flood: the water extent at the timeline time (last step with t_s <= t); the peak extent, faintly, in "Peak" view.
  const floodResult = isFloodResult(result)
  const floodControls = params.hazard === 'flood'
  const split = useMemo(() => (zonesNow ? splitZones(zonesNow) : null), [zonesNow])
  const stepNow = split && time != null ? floodStepAt(split.steps, time) : null
  const waterNow = useMemo(() => (stepNow ? [stepNow] : []), [stepNow])
  const waterData = time == null ? split?.peak ?? [] : waterNow

  // The three most-loaded bottleneck roads get a name label.
  const bottleneckLabels = useMemo(() => {
    if (!result) return []
    const seen = new Set<string>()
    const out: { position: [number, number]; text: string; priority: number }[] = []
    // Prefer major roads: a primary street at 1.2x load outranks a residential court at 1.4x.
    const score = (f: EdgeFeature) => f.properties.peak_load_ratio * (ROAD_WEIGHT[f.properties.road_class ?? ''] ?? 1)
    const sorted = result.edges.features.filter((f) => f.properties.is_bottleneck && f.properties.name).sort((a, b) => score(b) - score(a))
    for (const f of sorted) {
      const name = f.properties.name!
      if (seen.has(name)) continue
      const position = along(f.geometry.coordinates as [number, number][], 0.5)
      if (out.some((o) => distM(o.position, position) < 500)) continue // keep labels from stacking
      seen.add(name)
      out.push({ position, text: name, priority: 3 - out.length })
      if (out.length === 3) break
    }
    return out
  }, [result])

  const edgeLoadNow = useMemo(() => {
    const m = new globalThis.Map<number, number>()
    if (!result) return m
    for (const f of result.edges.features) {
      const id = f.properties.edge_id
      const v = time == null ? null : loadAt(result.timeline.edge_load[String(id)], time, result.timeline.step_s || 30)
      m.set(id, v ?? (time == null ? f.properties.peak_load_ratio : 0))
    }
    return m
  }, [result, time])

  const particleEdges: Particle[] = useMemo(() => {
    if (!result) return []
    return result.edges.features.map((edge) => {
      const path = edge.geometry.coordinates.map((c) => [c[0], c[1]] as [number, number])
      let lengthM = 0
      for (let i = 0; i < path.length - 1; i++) lengthM += distM(path[i], path[i + 1])
      return { path, lengthM: Math.max(lengthM, 20), edge }
    })
  }, [result])

  const particles = useMemo(() => {
    if (!toggles.traffic || particleEdges.length === 0) return []
    const out: { position: [number, number]; load: number }[] = []
    const budget = MAX_PARTICLES / Math.max(1, particleEdges.length)
    for (const p of particleEdges) {
      const load = edgeLoadNow.get(p.edge.properties.edge_id) ?? 0
      if (load < 0.03) continue
      const n = Math.min(Math.ceil(budget), Math.max(1, Math.round(load * (p.lengthM / 60))))
      const speedMps = 14 * Math.max(0.12, 1 - Math.min(load, 1.4) * 0.62) // congested roads crawl
      const base = (phase * speedMps) / p.lengthM
      for (let i = 0; i < n; i++) out.push({ position: along(p.path, (base + i / n) % 1), load })
    }
    return out
  }, [particleEdges, edgeLoadNow, phase, toggles.traffic])

  const buses = useMemo(() => result?.buses ?? [], [result])
  const busNow = useMemo(() => {
    if (time == null) return []
    return buses
      .map((b) => ({ bus: b, position: busPosition(b, time) }))
      .filter((x): x is { bus: Bus; position: [number, number] } => x.position != null && time <= (x.bus.arrival_s.at(-1) ?? 0) + 120)
  }, [buses, time])

  const pulse = (phase % 2) / 2
  const releasePos: [number, number] = [params.release_lon, params.release_lat]

  const glow = 0.5 + 0.5 * Math.sin(phase * 3)
  const zoneLayer = (id: string, zones: Zones, opacity: number) =>
    new GeoJsonLayer({
      id,
      data: splitZones(zones).chem,
      opacity,
      filled: true,
      stroked: true,
      getFillColor: (f) => [...COLORS.zone, (f.properties as { kind: string }).kind === 'isolation' ? 85 : 38],
      getLineColor: (f) => [...COLORS.zone, (f.properties as { kind: string }).kind === 'isolation' ? 255 : 200],
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      getDashArray: (f: { properties: { kind: string } }) => ((f.properties as { kind: string }).kind === 'protect' ? [6, 4] : [0, 0]),
      dashJustified: true,
      extensions: [new PathStyleExtension({ dash: true })],
      pickable: id === 'zones',
    })

  const layers = [
    dim &&
      new SolidPolygonLayer({
        id: 'dim-outside',
        data: dim.features,
        getPolygon: (f) => f.geometry.coordinates,
        getFillColor: [3, 5, 9, 120],
        opacity: zoneFade,
      }),
    split &&
      split.source.length > 0 &&
      new GeoJsonLayer({
        id: 'flood-source',
        data: split.source,
        opacity: zoneFade,
        filled: true,
        stroked: true,
        getFillColor: [...COLORS.lake, 46],
        getLineColor: [...COLORS.lake, 235],
        getLineWidth: 2,
        lineWidthUnits: 'pixels',
      }),
    toggles.heatmap &&
      derived &&
      new HeatmapLayer({
        id: 'need-help-heat',
        data: derived.blockPoints,
        getPosition: (d) => d.position,
        getWeight: (d) => Math.max(d.props.need_bus, 0) + d.props.vulnerability * 4,
        radiusPixels: 55,
        intensity: 1.2,
        threshold: 0.04,
        colorRange: [
          [32, 18, 77],
          [72, 30, 140],
          [128, 50, 168],
          [190, 70, 150],
          [240, 110, 120],
          [255, 190, 120],
        ],
        opacity: 0.75,
      }),
    toggles.blocks &&
      derived &&
      new GeoJsonLayer<BlockFeature['properties']>({
        id: 'blocks',
        data: derived.blockFeatures,
        filled: true,
        stroked: true,
        getFillColor: (f) => blockColor(f.properties, toggles.heatmap || toggles.frequency ? 60 : 150),
        getLineColor: (f) => (f.properties.decision === 'outside' ? [120, 130, 145, 40] : [10, 12, 16, 160]),
        lineWidthMinPixels: 0.6,
        pickable: !toggles.frequency,
        transitions: { getFillColor: 450 },
        updateTriggers: { getFillColor: [toggles.heatmap, toggles.frequency] },
      }),
    derived &&
      selectedBlock != null &&
      new GeoJsonLayer<BlockFeature['properties']>({
        id: 'block-selected',
        data: derived.blockFeatures.filter((f) => f.properties.block_id === selectedBlock),
        filled: true,
        stroked: true,
        getFillColor: [255, 255, 255, 40],
        getLineColor: [255, 255, 255, 255],
        getLineWidth: 3,
        lineWidthUnits: 'pixels',
      }),
    toggles.frequency &&
      blockGeo &&
      frequency &&
      new GeoJsonLayer<{ block_id: string }>({
        id: 'block-frequency',
        data: blockGeo.features,
        filled: true,
        stroked: true,
        getFillColor: (f) => frequencyColor((frequency.get(f.properties.block_id)?.share_shelter ?? 0) / frequencyMax),
        updateTriggers: { getFillColor: [frequency, frequencyMax] },
        getLineColor: [10, 12, 16, 120],
        lineWidthMinPixels: 0.5,
        pickable: true,
      }),
    split &&
      waterData.length > 0 &&
      new GeoJsonLayer({
        id: 'flood-water',
        data: waterData,
        opacity: zoneFade,
        filled: true,
        stroked: true,
        // Peak view: faint, so the whole danger area shows without hiding the blocks. Timeline: the water now, a bit stronger.
        getFillColor: [...COLORS.water, time == null ? 42 : 78],
        getLineColor: [...COLORS.waterEdge, time == null ? 120 : 190],
        getLineWidth: 1,
        lineWidthUnits: 'pixels',
        updateTriggers: { getFillColor: [time == null], getLineColor: [time == null] },
        transitions: { getFillColor: 300 },
      }),
    // Water sits over the block fills; redraw the block outlines on top so the blocks still read.
    floodResult &&
      toggles.blocks &&
      derived &&
      new GeoJsonLayer<BlockFeature['properties']>({
        id: 'blocks-outline',
        data: derived.blockFeatures,
        filled: false,
        stroked: true,
        getLineColor: (f) => (f.properties.decision === 'outside' ? [120, 130, 145, 40] : [10, 12, 16, 160]),
        lineWidthMinPixels: 0.6,
      }),
    split &&
      split.peak.length > 0 &&
      new GeoJsonLayer<unknown, PathStyleExtensionProps<unknown>>({
        id: 'flood-peak',
        data: split.peak,
        opacity: zoneFade,
        filled: false,
        stroked: true,
        getLineColor: [...COLORS.waterEdge, 200],
        getLineWidth: 1.5,
        lineWidthUnits: 'pixels',
        getDashArray: [6, 4],
        dashJustified: true,
        extensions: [new PathStyleExtension({ dash: true })],
      }),
    zoneHist.prev && zoneFade < 1 && zoneLayer('zones-prev', zoneHist.prev, 1 - zoneFade),
    result && zoneLayer('zones', result.zones, zoneFade),
    toggles.roads &&
      result &&
      new PathLayer<EdgeFeature>({
        id: 'edges-glow',
        data: result.edges.features.filter((f) => f.properties.is_bottleneck),
        getPath: (f) => f.geometry.coordinates as [number, number][],
        getColor: [255, 70, 70, Math.round(60 + 60 * glow)],
        getWidth: 20 + 8 * glow,
        updateTriggers: { getColor: [glow], getWidth: [glow] },
        widthUnits: 'pixels',
        capRounded: true,
        jointRounded: true,
      }),
    toggles.roads &&
      result &&
      new PathLayer<EdgeFeature>({
        id: 'edges',
        data: result.edges.features,
        getPath: (f) => f.geometry.coordinates as [number, number][],
        getColor: (f) => loadColor(edgeLoadNow.get(f.properties.edge_id) ?? 0),
        getWidth: (f) => (f.properties.is_bottleneck ? 10 : 3.5),
        widthUnits: 'pixels',
        widthMinPixels: 2,
        capRounded: true,
        jointRounded: true,
        pickable: true,
        updateTriggers: { getColor: [edgeLoadNow] },
        transitions: { getColor: 250 },
      }),
    toggles.roads &&
      result &&
      new PathLayer<EdgeFeature, PathStyleExtensionProps<EdgeFeature>>({
        id: 'edges-bottleneck-dash',
        data: result.edges.features.filter((f) => f.properties.is_bottleneck),
        getPath: (f) => f.geometry.coordinates as [number, number][],
        getColor: [255, 255, 255, 235],
        getWidth: 3,
        widthUnits: 'pixels',
        getDashArray: [2, 1.6],
        dashJustified: true,
        extensions: [new PathStyleExtension({ dash: true })],
      }),
    toggles.traffic &&
      new ScatterplotLayer({
        id: 'traffic',
        data: particles,
        getPosition: (d) => d.position,
        getFillColor: (d) => (d.load > 1 ? [255, 235, 220, 230] : [235, 245, 255, 200]),
        getRadius: 2.2,
        radiusUnits: 'pixels',
      }),
    rail &&
      new PathLayer({
        id: 'rail',
        data: rail.features,
        getPath: (f) => f.geometry.coordinates as [number, number][],
        getColor: hover?.layer === 'rail-hit' ? [230, 236, 245, 255] : [...COLORS.rail, 190],
        getWidth: 2.5,
        widthUnits: 'pixels',
        getDashArray: [4, 2.5],
        dashJustified: true,
        extensions: [new PathStyleExtension({ dash: true })],
        updateTriggers: { getColor: [hover?.layer] },
      }),
    rail &&
      !floodControls &&
      new PathLayer({
        id: 'rail-hit',
        data: rail.features,
        getPath: (f) => f.geometry.coordinates as [number, number][],
        getColor: [0, 0, 0, 0],
        getWidth: 18,
        widthUnits: 'pixels',
        pickable: true,
      }),
    toggles.buses &&
      new PathLayer<Bus, PathStyleExtensionProps<Bus>>({
        id: 'bus-routes',
        data: buses,
        getPath: (b) => b.path,
        getColor: (b) =>
          hoveredBus == null ? [...COLORS.bus, 115] : b.bus_id === hoveredBus ? [140, 200, 255, 255] : [...COLORS.bus, 30],
        getWidth: (b) => (b.bus_id === hoveredBus ? 5 : 2),
        widthUnits: 'pixels',
        getDashArray: [7, 3],
        dashJustified: true,
        extensions: [new PathStyleExtension({ dash: true })],
        capRounded: true,
        jointRounded: true,
        pickable: true,
        updateTriggers: { getColor: [hoveredBus], getWidth: [hoveredBus] },
      }),
    toggles.buses &&
      derived &&
      new ScatterplotLayer<BusStop>({
        id: 'bus-stops',
        data: derived.stops.filter((s) => s.position != null),
        getPosition: (s) => s.position!,
        getFillColor: (s) =>
          s.kind === 'garage' ? [40, 50, 66, 255] : s.kind === 'shelter' ? [...COLORS.onTime, 255] : s.late ? [...COLORS.late, 255] : [245, 248, 252, 255],
        getLineColor: (s) => (s.kind === 'pickup' ? (s.late ? [255, 200, 200, 255] : [...COLORS.bus, 255]) : [230, 236, 245, 255]),
        getRadius: (s) => (s.kind === 'pickup' ? (s.bus_id === hoveredBus ? 5 : 3.2) : 6),
        radiusUnits: 'pixels',
        stroked: true,
        lineWidthMinPixels: 1.5,
        updateTriggers: { getRadius: [hoveredBus] },
        pickable: true,
        opacity: hoveredBus == null ? 1 : 0.9,
      }),
    toggles.buses &&
      derived &&
      new TextLayer<BusStop>({
        id: 'stop-labels',
        data: hoveredBus == null ? [] : derived.stops.filter((s) => s.position != null && s.kind === 'pickup' && s.deadline_s != null && s.bus_id === hoveredBus),
        getPosition: (s) => s.position!,
        getText: (s) => `${s.late ? 'LATE, ' : ''}by ${floodResult ? fmtDuration(s.deadline_s ?? 0) : `${Math.round((s.deadline_s ?? 0) / 60)} min`}`,
        getSize: 11,
        getColor: (s) => (s.late ? [255, 150, 150, 255] : [220, 230, 245, 255]),
        getPixelOffset: [0, -14],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        outlineWidth: 3,
        outlineColor: [8, 10, 14, 255],
        fontSettings: { sdf: true },
      }),
    toggles.buses &&
      new ScatterplotLayer({
        id: 'bus-vehicles',
        data: busNow,
        getPosition: (d) => d.position,
        getFillColor: [140, 200, 255, 255],
        getLineColor: [8, 10, 14, 255],
        getRadius: 6,
        radiusUnits: 'pixels',
        stroked: true,
        lineWidthMinPixels: 2,
      }),
    !floodControls && new ScatterplotLayer({
      id: 'release-pulse',
      data: [releasePos],
      getPosition: (d) => d,
      getFillColor: [239, 68, 68, Math.round(120 * (1 - pulse))],
      getRadius: 8 + 30 * pulse,
      radiusUnits: 'pixels',
      updateTriggers: { getFillColor: [pulse], getRadius: [pulse] },
    }),
    !floodControls && new ScatterplotLayer({
      id: 'release',
      data: [releasePos],
      getPosition: (d) => d,
      getFillColor: [255, 255, 255, 255],
      getLineColor: [239, 68, 68, 255],
      getRadius: 6,
      radiusUnits: 'pixels',
      stroked: true,
      lineWidthMinPixels: 4,
    }),
    toggles.roads &&
      new TextLayer({
        id: 'bottleneck-labels',
        data: bottleneckLabels,
        getPosition: (d) => d.position,
        getText: (d) => d.text,
        // Sit beside the road, not on it: anchored at the label's corner and pushed off the line,
        // and the collision filter drops a label that would cover another one.
        getSize: 12.5,
        getColor: [247, 248, 248, 255],
        getTextAnchor: 'start',
        getAlignmentBaseline: 'bottom',
        getPixelOffset: [10, -10],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        background: true,
        getBackgroundColor: [15, 16, 17, 225],
        getBorderColor: [239, 68, 68, 200],
        getBorderWidth: 1,
        backgroundPadding: [6, 3, 6, 3],
        pickable: false,
      }),
    split &&
      split.labels.length > 0 &&
      new TextLayer({
        id: 'lake-labels',
        data: split.labels,
        getPosition: (d) => d.position,
        getText: (d) => d.text,
        getSize: 12.5,
        getColor: [247, 248, 248, 255],
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        background: true,
        getBackgroundColor: [15, 16, 17, 225],
        getBorderColor: [...COLORS.lake, 220],
        getBorderWidth: 1,
        backgroundPadding: [6, 3, 6, 3],
        opacity: zoneFade,
      }),
  ].filter(Boolean)

  const onHover = (info: PickingInfo) => {
    const id = info.layer?.id ?? null
    if (!info.picked || !id) {
      setHover(null)
      if (hoveredBus != null) setHoveredBus(null)
      return
    }
    setHover({ x: info.x, y: info.y, layer: id, object: info.object, coordinate: info.coordinate as [number, number] })
    const busId = id === 'bus-routes' ? (info.object as Bus).bus_id : id === 'bus-stops' ? (info.object as BusStop).bus_id : null
    if (busId !== hoveredBus) setHoveredBus(busId)
  }

  // Clicks are handled on the wrapper (not Deck's onClick) so a pan never counts as a click
  // and placement works even where deck's tap recognizer is flaky.
  const deckRef = useRef<DeckGLRef>(null)
  const downAt = useRef<[number, number] | null>(null)
  const onPointerDown = (e: React.PointerEvent) => {
    downAt.current = [e.clientX, e.clientY]
  }
  const onPointerUp = (e: React.PointerEvent) => {
    const start = downAt.current
    downAt.current = null
    const deck = deckRef.current?.deck
    if (!start || !deck || e.button !== 0 || Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 5) return
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    // 1) a bus route/stop opens its stop list; 2) the rail line moves the derailment;
    // 3) a block inside the zone opens its "why"; 4) anywhere else moves the derailment to the nearest rail.
    const top = deck.pickObject({ x, y, radius: 6, layerIds: ['bus-routes', 'bus-stops', 'rail-hit'] })
    if (top?.layer?.id === 'bus-routes' || top?.layer?.id === 'bus-stops') {
      const id = top.layer.id === 'bus-routes' ? (top.object as Bus).bus_id : (top.object as BusStop).bus_id
      onSelect({ kind: 'bus', id })
      return
    }
    if (!top && toggles.blocks && !toggles.frequency) {
      const b = deck.pickObject({ x, y, radius: 0, layerIds: ['blocks'] })
      const props = (b?.object as BlockFeature | undefined)?.properties
      if (props && props.decision !== 'outside') {
        onSelect({ kind: 'block', id: props.block_id })
        return
      }
    }
    onSelect(null)
    if (floodControls) return // a flood has no derailment pin to move
    if (railOnly && top?.layer?.id !== 'rail-hit') return
    const viewport = deck.getViewports()[0]
    if (!viewport) return
    const [lon, lat] = viewport.unproject([x, y])
    onPickRelease(lon, lat) // App snaps to the nearest rail line (or rejects if too far)
  }

  return (
    <div className="map-wrap" onPointerDown={onPointerDown} onPointerUp={onPointerUp}>
      <DeckGL
        ref={deckRef}
        initialViewState={initialViewState}
        controller={{ dragRotate: false }}
        layers={layers}
        onHover={onHover}
        pickingRadius={6}
        getCursor={({ isDragging }) => (isDragging ? 'grabbing' : hover?.layer === 'rail-hit' ? 'crosshair' : hover ? 'pointer' : 'grab')}
      >
        <Map mapStyle={BASEMAP} attributionControl={{ compact: true }} />
      </DeckGL>
      {hover && result && <Tooltip info={hover} result={result} derived={derived} edgeLoadNow={edgeLoadNow} time={time} frequency={frequency} />}
    </div>
  )
}
