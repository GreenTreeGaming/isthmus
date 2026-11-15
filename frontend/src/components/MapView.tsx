import { useEffect, useMemo, useRef, useState } from 'react'
import DeckGL, { type DeckGLRef } from '@deck.gl/react'
import { FlyToInterpolator, WebMercatorViewport, type PickingInfo } from '@deck.gl/core'
import { GeoJsonLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { PathStyleExtension, type PathStyleExtensionProps } from '@deck.gl/extensions'
import { Map, type MapEvent } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import '../lib/maplibreWorker'
import type { FeatureCollection, Polygon, Position } from 'geojson'
import type { BlockFeature, BlockFrequency, BlockGeoCollection, Bus, EdgeFeature, RailCollection, ScenarioParams, ScenarioResponse, ZoneFeature } from '../types'
import { COLORS, blockColor, frequencyColor, loadColor } from '../lib/colors'
import { busPosition, loadAt, type BusStop, type Derived } from '../lib/derive'
import { fmtDuration } from '../lib/format'
import { along, distM } from '../lib/geo'
import { floodStepAt, isFloodResult } from '../lib/hazard'
import { Tooltip, type HoverInfo } from './Tooltip'
import type { Selection } from './InfoCard'

// Default overview: the isthmus with Lake Mendota to the north and Lake Monona to the south.
const INITIAL_VIEW = { longitude: -89.392, latitude: 43.084, zoom: 12.4, pitch: 0, bearing: 0 }
const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const MAX_PARTICLES = 4000
const WATER = '#0e1a2b'
const SHORE = '#1e293b'

/** Tint the basemap's lakes navy with a shoreline, so the isthmus between Mendota and Monona reads at a glance. */
function styleWater(e: MapEvent) {
  const map = e.target
  const layers = map.getStyle()?.layers ?? []
  let first: (typeof layers)[number] | null = null
  for (const l of layers) {
    if (l.type !== 'fill' || !/water/i.test(l.id)) continue
    map.setPaintProperty(l.id, 'fill-color', /shadow/i.test(l.id) ? 'rgba(0,0,0,0)' : WATER)
    if (!/shadow/i.test(l.id)) first ??= l
  }
  if (first && 'source' in first && !map.getLayer('isthmus-shoreline')) {
    const idx = layers.indexOf(first)
    map.addLayer(
      {
        id: 'isthmus-shoreline',
        type: 'line',
        source: first.source as string,
        ...('source-layer' in first && first['source-layer'] ? { 'source-layer': first['source-layer'] as string } : {}),
        ...('filter' in first && first.filter ? { filter: first.filter } : {}),
        paint: { 'line-color': SHORE, 'line-width': 1.2 },
      },
      layers[idx + 1]?.id,
    )
  }
}
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
  stops: boolean // "Bus stops" focus mode: every stop drawn large
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
  /** Bumped by the logo: fly back to the default downtown overview. */
  home: number
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
  }
  splitCache.set(z, out)
  return out
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

export function MapView({ result, derived, rail, params, toggles, time, onPickRelease, hoveredBus: hoverBus, setHoveredBus, blockGeo, frequency, frequencyMax, selection, onSelect, fitTo, railOnly, home }: Props) {
  // Camera target: a new result's zone (fitTo) or, when the logo is clicked, the default overview.
  const [cam, setCam] = useState(() => ({ fitTo, home, view: fitView(fitTo) as ReturnType<typeof fitView> }))
  if (fitTo !== cam.fitTo || home !== cam.home) {
    setCam({
      fitTo,
      home,
      view: home !== cam.home ? { ...INITIAL_VIEW, transitionDuration: 1200, transitionInterpolator: new FlyToInterpolator() } : fitView(fitTo),
    })
  }
  const initialViewState = cam.view
  // Track the camera so road labels can be HTML (crisp glass pills) that follow the map.
  const [view, setView] = useState<{ longitude: number; latitude: number; zoom: number }>(INITIAL_VIEW)
  const [size, setSize] = useState<{ width: number; height: number }>({ width: window.innerWidth, height: window.innerHeight })
  const live = time != null // scrubbing or playing: traffic takes the stage
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
    const out: { position: [number, number]; text: string; load: number }[] = []
    // Prefer major roads: a primary street at 1.2x load outranks a residential court at 1.4x.
    const score = (f: EdgeFeature) => f.properties.peak_load_ratio * (ROAD_WEIGHT[f.properties.road_class ?? ''] ?? 1)
    const sorted = result.edges.features.filter((f) => f.properties.is_bottleneck && f.properties.name).sort((a, b) => score(b) - score(a))
    for (const f of sorted) {
      const name = f.properties.name!
      if (seen.has(name)) continue
      const position = along(f.geometry.coordinates as [number, number][], 0.5)
      if (out.some((o) => distM(o.position, position) < 500)) continue // keep labels from stacking
      seen.add(name)
      out.push({ position, text: name, load: f.properties.peak_load_ratio })
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
      opacity: opacity * (live ? 0.45 : 1),
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
        getFillColor: [3, 5, 9, live ? 150 : 90],
        updateTriggers: { getFillColor: [live] },
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
        // Rising lake: a quiet teal wash with a hairline edge (no neon outline).
        getFillColor: [14, 116, 144, 64],
        getLineColor: [56, 189, 248, 115],
        getLineWidth: 1,
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
        // Light wash (~0.32) with a thin edge of the same colour, so streets and routes stay readable.
        getFillColor: (f) => blockColor(f.properties, toggles.heatmap || toggles.frequency ? 50 : live ? 40 : 82),
        getLineColor: (f) => (f.properties.decision === 'outside' ? [120, 130, 145, 28] : blockColor(f.properties, live ? 60 : 120)),
        lineWidthMinPixels: 0.5,
        pickable: !toggles.frequency,
        transitions: { getFillColor: 450 },
        updateTriggers: { getFillColor: [toggles.heatmap, toggles.frequency, live], getLineColor: [live] },
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
        // Flooded land: slate blue (0.35 while the timeline runs, a little lighter in Peak view) and a 1px edge.
        getFillColor: [30, 64, 175, time == null ? 72 : 89],
        getLineColor: [56, 189, 248, 115],
        getLineWidth: 1,
        lineWidthUnits: 'pixels',
        updateTriggers: { getFillColor: [time == null] },
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
    // While the timeline runs, a faint dashed line shows how far the water will reach at the peak.
    split &&
      split.peak.length > 0 &&
      time != null &&
      new GeoJsonLayer<unknown, PathStyleExtensionProps<unknown>>({
        id: 'flood-peak',
        data: split.peak,
        opacity: zoneFade,
        filled: false,
        stroked: true,
        getLineColor: [56, 189, 248, 70],
        getLineWidth: 1,
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
        getColor: (f) => {
          const load = edgeLoadNow.get(f.properties.edge_id) ?? 0
          return loadColor(load, live ? (load < 0.05 ? 70 : 255) : 235)
        },
        getWidth: (f) => (f.properties.is_bottleneck ? (live ? 11 : 9) : live ? 4.5 : 3),
        widthUnits: 'pixels',
        widthMinPixels: 2,
        capRounded: true,
        jointRounded: true,
        pickable: true,
        updateTriggers: { getColor: [edgeLoadNow, live], getWidth: [live] },
        transitions: { getColor: 250, getWidth: 300 },
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
        getRadius: live ? 2.8 : 2.2,
        radiusUnits: 'pixels',
        updateTriggers: { getRadius: [live] },
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
        // Quiet by default (small muted blue dots); a hovered/selected bus or "Bus stops" focus enlarges them.
        getFillColor: (s) => {
          const focus = toggles.stops || s.bus_id === hoveredBus
          if (s.kind === 'garage') return [40, 50, 66, 255]
          if (s.kind === 'shelter') return [...COLORS.onTime, 230]
          if (s.late) return [...COLORS.late, 255]
          return focus ? [245, 248, 252, 255] : [59, 130, 246, 153]
        },
        getLineColor: (s) => (s.kind === 'pickup' ? [...COLORS.bus, 255] : [230, 236, 245, 220]),
        getLineWidth: (s) => (s.kind !== 'pickup' || toggles.stops || s.bus_id === hoveredBus ? 1.5 : 0),
        lineWidthUnits: 'pixels',
        getRadius: (s) => (s.kind === 'pickup' ? (toggles.stops || s.bus_id === hoveredBus ? 4.5 : 2.4) : 5),
        radiusUnits: 'pixels',
        stroked: true,
        updateTriggers: { getRadius: [hoveredBus, toggles.stops], getFillColor: [hoveredBus, toggles.stops], getLineWidth: [hoveredBus, toggles.stops] },
        pickable: true,
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
        onViewStateChange={({ viewState }) => {
          const v = viewState as { longitude: number; latitude: number; zoom: number }
          // deck may call this while it renders (camera transitions), so update React state just after.
          queueMicrotask(() => setView({ longitude: v.longitude, latitude: v.latitude, zoom: v.zoom }))
        }}
        onResize={(sz) => queueMicrotask(() => setSize(sz))}
        controller={{ dragRotate: false }}
        layers={layers}
        onHover={onHover}
        pickingRadius={6}
        getCursor={({ isDragging }) => (isDragging ? 'grabbing' : hover?.layer === 'rail-hit' ? 'crosshair' : hover ? 'pointer' : 'grab')}
      >
        <Map mapStyle={BASEMAP} attributionControl={{ compact: true }} onLoad={styleWater} />
      </DeckGL>
      {toggles.roads && bottleneckLabels.length > 0 && (
        <div className={`road-pins ${live ? 'live' : ''}`} aria-hidden>
          {bottleneckLabels.map((l) => {
            const vp = new WebMercatorViewport({ ...view, width: size.width, height: size.height })
            const [x, y] = vp.project(l.position)
            if (x < -200 || y < -50 || x > size.width + 50 || y > size.height + 50) return null
            return (
              <div key={l.text} className="road-pin" style={{ transform: `translate(${x}px, ${y}px)` }}>
                <i className="road-anchor" />
                <span className="road-pill">
                  <i className={`sev ${l.load > 1.2 ? 'red' : 'amber'}`} />
                  {l.text}
                </span>
              </div>
            )
          })}
        </div>
      )}
      {hover && result && <Tooltip info={hover} result={result} derived={derived} edgeLoadNow={edgeLoadNow} time={time} frequency={frequency} />}
    </div>
  )
}
