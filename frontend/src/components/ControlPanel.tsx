import type { ScenarioParams } from '../types'
import { fmtRise } from '../lib/hazard'
import { Tip } from './Tip'
import { WindDial } from './WindDial'

interface Props {
  params: ScenarioParams
  update: <K extends keyof ScenarioParams>(key: K, value: ScenarioParams[K]) => void
  onRun: () => void
  onReset: () => void
  loading: boolean
  autoRun: boolean
  setAutoRun: (v: boolean) => void
  pickHint: string | null
  railName: string | null
  place: string
  /** Plain-language summary of the current plan, shown above Run. */
  plan?: React.ReactNode
}

function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} role="radio" aria-checked={value === v} className={value === v ? 'on' : ''} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  )
}

function Slider({ label, value, display, min, max, step, onChange, tip }: { label: string; value: number; display: string; min: number; max: number; step: number; onChange: (v: number) => void; tip?: string }) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <label className="slider">
      <div className="slider-head">
        {tip ? <span className="slider-label">{label} <Tip text={tip} /></span> : <span>{label}</span>}
        <b>{display}</b>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} style={{ '--pct': `${pct}%` } as React.CSSProperties} />
    </label>
  )
}

export function ControlPanel({ params, update, onRun, onReset, loading, autoRun, setAutoRun, pickHint, railName, place, plan }: Props) {
  const flood = params.hazard === 'flood'
  return (
    <aside className="panel controls">
      <section>
        <h3>Hazard <Tip text="Chemical spill: a tank car derails on a rail line and releases toxic gas. Flood: Lake Mendota and/or Lake Monona rise over several hours and water spreads onto low ground." /></h3>
        <Segmented label="Hazard" value={params.hazard} options={[['chemical', 'Chemical spill'], ['flood', 'Flood']]} onChange={(v) => update('hazard', v)} />
      </section>

      {flood ? (
      <section>
        <h3>Flood <Tip text="Which lake rises. Lake Monona drains through the Yahara River, so choosing it also raises the river below it. The whole isthmus sits between the two lakes." /></h3>
        <Segmented
          label="Flood source"
          value={params.flood_source}
          options={[['mendota', 'Mendota'], ['monona', 'Monona + Yahara'], ['both', 'Both lakes']]}
          onChange={(v) => update('flood_source', v)}
        />
        <Slider label="Lake rise" value={params.flood_rise_m} display={fmtRise(params.flood_rise_m)} min={0.25} max={3} step={0.25} onChange={(v) => update('flood_rise_m', v)} tip="How far the lakes rise above their normal summer level. In August 2018 heavy rain pushed both lakes to record highs and flooded parts of the east isthmus." />
        <Slider label="Time to peak" value={params.flood_peak_h} display={`${params.flood_peak_h} h`} min={1} max={48} step={1} onChange={(v) => update('flood_peak_h', v)} tip="Hours from the alert until the water peaks; it rises steadily until then. A fast rise leaves less time to drive out, so more blocks are told to stay and move upstairs." />
      </section>
      ) : (
      <>
      <section>
        <h3>Release point <Tip text="Click a rail line on the map to move the derailment. It always snaps to the nearest track; the demo uses the line nearest the Capitol." /></h3>
        {pickHint && (
          <div className="pick-hint warn">
            <span className="pin-dot" />
            {pickHint}
          </div>
        )}
        <div className="release-where" title={`${params.release_lat.toFixed(4)}°N, ${Math.abs(params.release_lon).toFixed(4)}°W`}>
          <span className="pin-dot" />
          <span>
            <b>{railName ?? 'Rail line'}</b>
            <span>{place}</span>
          </span>
        </div>
      </section>

      <section>
        <h3>Chemical &amp; spill <Tip text="Danger-zone distances come from the 2024 Emergency Response Guidebook. A large spill is a whole rail tank car; for chlorine at night in light wind the zone reaches 7+ miles." /></h3>
        <div className="seg-row">
          <Segmented label="Chemical" value={params.chemical} options={[['chlorine', 'Chlorine'], ['ammonia', 'Ammonia']]} onChange={(v) => update('chemical', v)} />
          <Segmented label="Spill size" value={params.spill_size} options={[['small', 'Small'], ['large', 'Large']]} onChange={(v) => update('spill_size', v)} />
        </div>
      </section>

      <section>
        <h3>Wind <Tip text="Direction decides where the gas goes. Speed cuts both ways: light wind makes a bigger zone but slow gas, so many can drive out; strong wind shrinks the zone but the gas arrives so fast that most people must shelter." /></h3>
        <WindDial fromDeg={params.wind_from_deg} onChange={(d) => update('wind_from_deg', d)} />
        <Slider label="Wind speed" value={params.wind_speed_mps} display={`${params.wind_speed_mps.toFixed(1)} m/s`} min={0.5} max={15} step={0.5} onChange={(v) => update('wind_speed_mps', v)} />
      </section>
      </>
      )}

      <section>
        <h3>Time of day <Tip text="Night: residents at home (2020 Census). Day: adds downtown workers (LEHD jobs data). Game day: adds about 75,000 people around Camp Randall." /></h3>
        <Segmented label="Time of day" value={params.time_of_day} options={[['night', 'Night'], ['day', 'Day'], ['gameday', 'Game day']]} onChange={(v) => update('time_of_day', v)} />
      </section>

      <section>
        <h3>Response <Tip text={`Buses: Madison Metro's fleet, 60 seats each, leaving the garage 10 min after the alert. Compliance: share of people who follow the order. Contraflow: major roads run outbound only.${flood ? ' Flooded roads are closed.' : ''}`} /></h3>
        <Slider label="Buses available" value={params.bus_count} display={`${params.bus_count}`} min={0} max={80} step={1} onChange={(v) => update('bus_count', v)} />
        <Slider label="Compliance" value={params.compliance} display={`${Math.round(params.compliance * 100)}%`} min={0.6} max={1} step={0.01} onChange={(v) => update('compliance', v)} />
        <label className="toggle compact">
          <input type="checkbox" checked={params.contraflow} onChange={(e) => update('contraflow', e.target.checked)} />
          <span className="switch" />
          <span title="Reverse inbound lanes on main arterials">Contraflow</span>
        </label>
      </section>

      <div className="run-footer">
      {plan}
      <div className="run-row">
        <button className="run" onClick={onRun} disabled={loading}>
          {loading ? <span className="spinner" /> : '▶'} {loading ? 'Running…' : 'Run scenario'}
        </button>
        <button className="ghost" onClick={onReset} title="Reset to defaults">
          Reset
        </button>
        <label className="toggle compact auto-run" title="Re-run automatically whenever a control changes">
          <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} aria-label="Auto-run on change" />
          <span className="switch" />
          <span>Auto</span>
        </label>
      </div>
      </div>
    </aside>
  )
}
