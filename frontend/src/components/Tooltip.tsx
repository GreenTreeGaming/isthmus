import type { BlockFeature, BlockFrequency, Bus, EdgeFeature, ScenarioResponse } from '../types'
import type { BusStop, Derived } from '../lib/derive'
import { COLORS, blockColor, loadColor, rgb } from '../lib/colors'
import { fmtClock, fmtDuration, fmtInt, fmtPct } from '../lib/format'

export interface HoverInfo {
  x: number
  y: number
  layer: string
  object: unknown
  coordinate?: [number, number]
}

interface Props {
  info: HoverInfo
  result: ScenarioResponse
  derived: Derived | null
  edgeLoadNow: Map<number, number>
  time: number | null
  frequency: Map<string, BlockFrequency> | null
}

function Row({ k, v, tone }: { k: string; v: React.ReactNode; tone?: 'bad' | 'good' }) {
  return (
    <div className="tt-row">
      <span>{k}</span>
      <b className={tone}>{v}</b>
    </div>
  )
}

function Body({ info, result, derived, edgeLoadNow, time, frequency }: Props) {
  switch (info.layer) {
    case 'block-frequency': {
      const id = (info.object as { properties: { block_id: string } }).properties.block_id
      const f = frequency?.get(id)
      return (
        <>
          <div className="tt-title">Across all simulated derailments</div>
          <div className="tt-sub">Census block {id}</div>
          <Row k="Told to shelter in place" v={f ? fmtPct(f.share_shelter) : '—'} />
          <Row k="Told to evacuate" v={f ? fmtPct(f.share_evacuate) : '—'} />
          <Row k="Unaffected" v={f ? fmtPct(Math.max(0, 1 - f.share_shelter - f.share_evacuate)) : '—'} />
          <div className="tt-foot">Share of batch scenarios (gold table).</div>
        </>
      )
    }
    case 'blocks': {
      const p = (info.object as BlockFeature).properties
      const label =
        p.decision === 'shelter' ? 'Shelter in place' : p.decision === 'evacuate' ? `Evacuate · wave ${(p.wave ?? 0) + 1}` : 'Outside the zone'
      return (
        <>
          <div className="tt-title">
            <i className="swatch" style={{ background: rgb(blockColor(p, 255)) }} />
            {label}
          </div>
          <div className="tt-sub">Census block {p.block_id}</div>
          {p.decision !== 'outside' && (
            <>
              <Row k="Plume arrives" v={fmtDuration(p.plume_arrival_s)} />
              <Row k="Est. time to get out" v={fmtDuration(p.est_exit_time_s)} tone={p.est_exit_time_s != null && p.plume_arrival_s != null && p.est_exit_time_s > p.plume_arrival_s ? 'bad' : undefined} />
            </>
          )}
          {p.decision === 'evacuate' && (
            <>
              <Row k="Driving (vehicles)" v={fmtInt(p.drivers)} />
              <Row k="Walking" v={fmtInt(p.walkers)} />
            </>
          )}
          {p.decision !== 'outside' && <Row k="Residents who may need a bus" v={`≈ ${fmtInt(p.need_bus)}`} />}
          <Row k="Area need-help index" v={fmtPct(p.vulnerability)} />
          <div className="tt-foot">Area-level estimate — not individuals.</div>
        </>
      )
    }
    case 'edges': {
      const p = (info.object as EdgeFeature).properties
      const now = edgeLoadNow.get(p.edge_id) ?? 0
      return (
        <>
          <div className="tt-title">
            <i className="swatch" style={{ background: rgb(loadColor(p.peak_load_ratio)) }} />
            {p.name ?? `Road segment ${p.edge_id}`}
            {p.is_bottleneck && <span className="pill bad">Bottleneck</span>}
          </div>
          {time != null && <Row k={`Load at ${fmtClock(time)}`} v={fmtPct(now)} tone={now > 1 ? 'bad' : undefined} />}
          <Row k="Peak load vs. capacity" v={fmtPct(p.peak_load_ratio)} tone={p.peak_load_ratio > 1 ? 'bad' : undefined} />
          <Row k="Vehicles over evacuation" v={fmtInt(p.flow_veh)} />
          <Row k="Backs up at" v={p.congested_at_s == null ? 'never' : fmtClock(p.congested_at_s)} />
        </>
      )
    }
    case 'bus-routes': {
      const b = info.object as Bus
      const late = derived?.busLate.get(b.bus_id) ?? 0
      const picked = Math.max(0, ...b.load)
      return (
        <>
          <div className="tt-title">
            <i className="swatch" style={{ background: rgb(COLORS.bus) }} />
            Bus {b.bus_id + 1}
            {late > 0 ? <span className="pill bad">{late} late</span> : <span className="pill good">on time</span>}
          </div>
          <Row k="Stops" v={b.stops.length} />
          <Row k="Peak on board" v={fmtInt(picked)} />
          <Row k="Arrives at shelter" v={fmtClock(b.arrival_s.at(-1) ?? 0)} />
          <div className="tt-sub mono">{b.stops.join(' → ')}</div>
        </>
      )
    }
    case 'bus-stops': {
      const s = info.object as BusStop
      const title = s.kind === 'garage' ? 'Bus garage' : s.kind === 'shelter' ? 'Shelter / drop-off' : 'Pickup'
      return (
        <>
          <div className="tt-title">
            {title} · Bus {s.bus_id + 1}
            {s.kind === 'pickup' && s.deadline_s != null && (s.late ? <span className="pill bad">after plume</span> : <span className="pill good">before plume</span>)}
          </div>
          <div className="tt-sub mono">{s.stop_id}</div>
          <Row k="Bus arrives" v={fmtClock(s.arrival_s)} />
          {s.kind === 'pickup' && <Row k="Pickup deadline (plume)" v={s.deadline_s == null ? '—' : fmtClock(s.deadline_s)} tone={s.late ? 'bad' : 'good'} />}
          <Row k="On board after stop" v={fmtInt(s.load)} />
        </>
      )
    }
    case 'zones': {
      const kind = (info.object as { properties: { kind: string } }).properties.kind
      return (
        <>
          <div className="tt-title">
            <i className="swatch" style={{ background: rgb(COLORS.zone) }} />
            {kind === 'isolation' ? 'Initial isolation zone' : 'Downwind protective-action zone'}
          </div>
          <div className="tt-sub">
            {kind === 'isolation' ? 'Everyone in this circle moves out or shelters immediately.' : 'Area the plume may reach, per ERG guidance.'}
          </div>
          <div className="tt-foot">Click to move the release to the nearest rail line.</div>
        </>
      )
    }
    case 'rail-hit':
      return (
        <>
          <div className="tt-title">{(info.object as { properties: { name: string | null } }).properties.name ?? 'Rail line'}</div>
          <div className="tt-sub">Click to place the derailment here.</div>
        </>
      )
    default:
      void result
      return null
  }
}

export function Tooltip(props: Props) {
  const body = Body(props)
  if (!body) return null
  const { x, y } = props.info
  const flipX = x > window.innerWidth - 320
  const flipY = y > window.innerHeight - 260
  return (
    <div
      className="tooltip"
      style={{
        left: flipX ? undefined : x + 14,
        right: flipX ? window.innerWidth - x + 14 : undefined,
        top: flipY ? undefined : y + 14,
        bottom: flipY ? window.innerHeight - y + 14 : undefined,
      }}
    >
      {body}
    </div>
  )
}
