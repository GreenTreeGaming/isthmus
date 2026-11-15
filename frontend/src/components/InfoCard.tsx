import type { BlockProps, Bus } from '../types'
import type { BusStop, Derived } from '../lib/derive'
import { COLORS, blockColor, rgb } from '../lib/colors'
import { explainBlock, type WaveTiming } from '../lib/explain'
import { fmtClock, fmtInt, fmtPct } from '../lib/format'

export type Selection = { kind: 'block'; id: string } | { kind: 'bus'; id: number }

interface Props {
  selection: Selection
  blocks: Record<string, Omit<BlockProps, 'block_id'>>
  buses: Bus[]
  derived: Derived | null
  timing: WaveTiming
  /** Flood result: water instead of gas. */
  flood: boolean
  onClose: () => void
  onHoverBus: (id: number | null) => void
}

function BlockCard({ p, timing, flood }: { p: BlockProps; timing: WaveTiming; flood: boolean }) {
  const e = explainBlock(p, timing, flood)
  return (
    <>
      <div className={`why-head ${e.tone}`}>
        <i className="swatch lg" style={{ background: rgb(blockColor(p, 255)) }} />
        <div>
          <div className="why-title">{e.headline}</div>
          <div className="why-sentence">{e.sentence}</div>
        </div>
      </div>
      <p className="why-body">{e.why}</p>
      {p.decision !== 'outside' && (
        <div className="why-facts">
          {p.decision === 'evacuate' && (
            <>
              <div><b>{fmtInt(p.drivers)}</b><span>vehicles leaving</span></div>
              <div><b>{fmtInt(p.walkers)}</b><span>walking out</span></div>
            </>
          )}
          <div><b>≈ {fmtInt(p.need_bus)}</b><span>may need a bus</span></div>
          <div><b>{fmtPct(p.vulnerability)}</b><span>need-help index</span></div>
        </div>
      )}
      <div className="why-foot">Census block {p.block_id} · area-level estimate, not individuals.</div>
    </>
  )
}

function stopLabel(s: BusStop, pickupNo: number) {
  if (s.kind === 'garage') return 'Leaves garage'
  if (s.kind === 'shelter') return 'Drop-off at shelter'
  return `Pickup ${pickupNo}`
}

function BusCard({ bus, stops, flood }: { bus: Bus; stops: BusStop[]; flood: boolean }) {
  const Hz = flood ? 'Water' : 'Gas'
  const late = stops.filter((s) => s.late).length
  const pickupNo = stops.map((_, i) => stops.slice(0, i + 1).filter((x) => x.kind === 'pickup').length)
  return (
    <>
      <div className="why-head bus">
        <i className="swatch lg" style={{ background: rgb(COLORS.bus) }} />
        <div>
          <div className="why-title">Bus {bus.bus_id + 1}</div>
          <div className="why-sentence">
            {stops.filter((s) => s.kind === 'pickup').length} pickups ·{' '}
            {late > 0 ? <span className="bad">{late} after the deadline</span> : <span className="good">each before its {Hz.toLowerCase()} deadline</span>}
          </div>
        </div>
      </div>
      <table className="stop-table">
        <thead>
          <tr><th>Stop</th><th>Bus at</th><th>{Hz} at</th><th>Aboard</th></tr>
        </thead>
        <tbody>
          {stops.map((s, i) => {
            return (
              <tr key={s.index} className={s.late ? 'late' : ''}>
                <td>{stopLabel(s, pickupNo[i])}</td>
                <td className="mono">{fmtClock(s.arrival_s)}</td>
                <td className="mono">{s.kind !== 'pickup' || s.deadline_s == null ? '—' : fmtClock(s.deadline_s)}</td>
                <td className="mono">{fmtInt(s.load)}{s.late && <span className="pill bad">late</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="why-foot">
        "{Hz} at" = the deadline the bus router enforced for that stop. Residents no bus could reach in time are counted as "left behind" on
        the Need a bus card. Times from the alert.
      </div>
    </>
  )
}

export function InfoCard({ selection, blocks, buses, derived, timing, flood, onClose, onHoverBus }: Props) {
  let body: React.ReactNode = null
  if (selection.kind === 'block') {
    const run = blocks[selection.id]
    if (run) body = <BlockCard p={{ ...run, block_id: selection.id }} timing={timing} flood={flood} />
  } else {
    const bus = buses.find((b) => b.bus_id === selection.id)
    if (bus) body = <BusCard bus={bus} stops={(derived?.stops ?? []).filter((s) => s.bus_id === bus.bus_id)} flood={flood} />
  }
  if (!body) return null
  return (
    <aside
      className="panel info-card"
      onMouseEnter={() => selection.kind === 'bus' && onHoverBus(selection.id)}
      onMouseLeave={() => selection.kind === 'bus' && onHoverBus(null)}
    >
      <div className="info-kicker">
        Why?
        <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {body}
    </aside>
  )
}
