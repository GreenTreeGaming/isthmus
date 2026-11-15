import { useState } from 'react'
import { COLORS, FREQUENCY_GRADIENT_CSS, LOAD_GRADIENT_CSS, rgb } from '../lib/colors'
import type { LayerToggles } from './MapView'

interface Props {
  toggles: LayerToggles
  setToggle: (k: keyof LayerToggles, v: boolean) => void
  frequencyMax: number | null // null = no batch results yet
  hidden?: boolean
  /** Flood result: water and rising-lake swatches instead of the chemical danger zone. */
  flood?: boolean
}

const LAYERS: [keyof LayerToggles, string][] = [
  ['blocks', 'Decisions by block'],
  ['roads', 'Road load'],
  ['traffic', 'Animated traffic'],
  ['buses', 'Bus routes'],
  ['stops', 'Bus stops (focus)'],
  ['heatmap', 'Residents who need help'],
  ['frequency', 'How often told to shelter'],
]

export function Legend({ toggles, setToggle, frequencyMax, hidden, flood = false }: Props) {
  // On short (projector) screens the layer switches start folded so the legend never covers the cards.
  const [layersOpen, setLayersOpen] = useState(() => window.innerHeight >= 900)
  const [open, setOpen] = useState(() => window.innerHeight >= 820)
  return (
    <div className={`panel legend ${hidden ? 'hidden' : ''} ${open ? 'open' : ''}`}>
      <button className="legend-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>Legend</span>
        <svg className="chev" viewBox="0 0 12 12" width="12" height="12" aria-hidden><path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      <div className="fold"><div className="fold-inner">
      <div className="legend-group">
        <div className="legend-item"><i className="sw" style={{ background: rgb(COLORS.shelter, 0.85) }} />{flood ? 'Stay, move upstairs' : 'Shelter in place'}</div>
        <div className="legend-item">
          <span className="waves">
            {COLORS.waves.map((c, i) => <i key={i} style={{ background: rgb(c) }} />)}
          </span>
          Evacuate, waves 1–4
        </div>
        <div className="legend-item"><i className="sw" style={{ background: rgb(COLORS.outside, 0.5) }} />Outside zone</div>
        {flood ? (
          <>
            <div className="legend-item"><i className="sw water" />Flood water</div>
            <div className="legend-item"><i className="sw flood-peak" />Flooded at the peak</div>
            <div className="legend-item"><i className="sw lake" />Rising lake</div>
          </>
        ) : (
          <div className="legend-item"><i className="sw zone" />Danger zone</div>
        )}
      </div>
      <div className="legend-group">
        <div className="legend-label">Road load</div>
        <div className="gradient" style={{ background: LOAD_GRADIENT_CSS }} />
        <div className="gradient-scale"><span>free</span><span>at capacity</span><span>over</span></div>
        <div className="legend-item"><i className="line glow" />Choke point</div>
        <div className="legend-item"><i className="line bus" />Bus route</div>
      </div>
      {toggles.frequency && frequencyMax != null && (
        <div className="legend-group">
          <div className="legend-label">Told to shelter, across all scenarios</div>
          <div className="gradient" style={{ background: FREQUENCY_GRADIENT_CSS }} />
          <div className="gradient-scale"><span>0%</span><span>{Math.round(frequencyMax * 100)}%</span></div>
        </div>
      )}
      <div className="legend-group layers">
        <button className="legend-fold" onClick={() => setLayersOpen((o) => !o)} aria-expanded={layersOpen}>
          Map layers <svg className={`chev ${layersOpen ? 'up' : ''}`} viewBox="0 0 12 12" width="12" height="12" aria-hidden><path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        {layersOpen && LAYERS.map(([k, label]) => (
          <label
            key={k}
            className={`toggle compact ${k === 'frequency' && frequencyMax == null ? 'disabled' : ''}`}
            title={k === 'frequency' && frequencyMax == null ? 'Available after the batch run writes data/gold/block_frequency.json' : undefined}
          >
            <input
              type="checkbox"
              checked={toggles[k]}
              disabled={k === 'frequency' && frequencyMax == null}
              onChange={(e) => setToggle(k, e.target.checked)}
            />
            <span className="switch" />
            <span>{label}</span>
          </label>
        ))}
      </div>
      </div></div>
    </div>
  )
}
