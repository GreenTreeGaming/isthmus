import { COLORS, FREQUENCY_GRADIENT_CSS, LOAD_GRADIENT_CSS, rgb } from '../lib/colors'
import type { LayerToggles } from './MapView'

interface Props {
  toggles: LayerToggles
  setToggle: (k: keyof LayerToggles, v: boolean) => void
  frequencyMax: number | null // null = no batch results yet
  hidden?: boolean
}

const LAYERS: [keyof LayerToggles, string][] = [
  ['blocks', 'Decisions by block'],
  ['roads', 'Road load'],
  ['traffic', 'Animated traffic'],
  ['buses', 'Bus routes'],
  ['heatmap', 'Residents who need help'],
  ['frequency', 'How often told to shelter'],
]

export function Legend({ toggles, setToggle, frequencyMax, hidden }: Props) {
  return (
    <div className={`panel legend ${hidden ? 'hidden' : ''}`}>
      <div className="legend-group">
        <div className="legend-item"><i className="sw" style={{ background: rgb(COLORS.shelter, 0.85) }} />Shelter in place</div>
        <div className="legend-item">
          <span className="waves">
            {COLORS.waves.map((c, i) => <i key={i} style={{ background: rgb(c) }} />)}
          </span>
          Evacuate · wave 1 → 4
        </div>
        <div className="legend-item"><i className="sw" style={{ background: rgb(COLORS.outside, 0.5) }} />Outside zone</div>
        <div className="legend-item"><i className="sw zone" />Isolation / protective zone</div>
      </div>
      <div className="legend-group">
        <div className="legend-label">Road load vs. capacity</div>
        <div className="gradient" style={{ background: LOAD_GRADIENT_CSS }} />
        <div className="gradient-scale"><span>0%</span><span>100%</span><span>140%+</span></div>
        <div className="legend-item"><i className="line glow" />Bottleneck</div>
        <div className="legend-item"><i className="line bus" />Bus route (hover for deadlines)</div>
        <div className="legend-item"><i className="stop late" />Pickup after plume arrives</div>
      </div>
      {toggles.frequency && frequencyMax != null && (
        <div className="legend-group">
          <div className="legend-label">Told to shelter, across all scenarios</div>
          <div className="gradient" style={{ background: FREQUENCY_GRADIENT_CSS }} />
          <div className="gradient-scale"><span>0%</span><span>{Math.round(frequencyMax * 100)}%</span></div>
        </div>
      )}
      <div className="legend-group layers">
        {LAYERS.map(([k, label]) => (
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
    </div>
  )
}
