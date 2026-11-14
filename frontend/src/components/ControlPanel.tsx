import type { ScenarioParams } from '../types'
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

function Slider({ label, value, display, min, max, step, onChange }: { label: string; value: number; display: string; min: number; max: number; step: number; onChange: (v: number) => void }) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <label className="slider">
      <div className="slider-head">
        <span>{label}</span>
        <b>{display}</b>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} style={{ '--pct': `${pct}%` } as React.CSSProperties} />
    </label>
  )
}

export function ControlPanel({ params, update, onRun, onReset, loading, autoRun, setAutoRun, pickHint }: Props) {
  return (
    <aside className="panel controls">
      <section>
        <h3>Release point</h3>
        <div className={`pick-hint ${pickHint ? 'warn' : ''}`}>
          <span className="pin-dot" />
          {pickHint ?? 'Click a rail line on the map to place the derailment.'}
        </div>
        <div className="coords mono">
          {params.release_lat.toFixed(4)}°N, {Math.abs(params.release_lon).toFixed(4)}°W
        </div>
      </section>

      <section>
        <h3>Chemical &amp; spill</h3>
        <Segmented label="Chemical" value={params.chemical} options={[['chlorine', 'Chlorine'], ['ammonia', 'Ammonia']]} onChange={(v) => update('chemical', v)} />
        <Segmented label="Spill size" value={params.spill_size} options={[['small', 'Small spill'], ['large', 'Large spill']]} onChange={(v) => update('spill_size', v)} />
      </section>

      <section>
        <h3>Wind</h3>
        <WindDial fromDeg={params.wind_from_deg} onChange={(d) => update('wind_from_deg', d)} />
        <Slider label="Wind speed" value={params.wind_speed_mps} display={`${params.wind_speed_mps.toFixed(1)} m/s`} min={0.5} max={15} step={0.5} onChange={(v) => update('wind_speed_mps', v)} />
      </section>

      <section>
        <h3>Time of day</h3>
        <Segmented label="Time of day" value={params.time_of_day} options={[['night', 'Night'], ['day', 'Day'], ['gameday', 'Game day']]} onChange={(v) => update('time_of_day', v)} />
      </section>

      <section>
        <h3>Response</h3>
        <Slider label="Buses available" value={params.bus_count} display={`${params.bus_count}`} min={0} max={80} step={1} onChange={(v) => update('bus_count', v)} />
        <Slider label="Compliance" value={params.compliance} display={`${Math.round(params.compliance * 100)}%`} min={0.6} max={1} step={0.01} onChange={(v) => update('compliance', v)} />
        <label className="toggle">
          <input type="checkbox" checked={params.contraflow} onChange={(e) => update('contraflow', e.target.checked)} />
          <span className="switch" />
          <span>
            Contraflow
            <small>Reverse inbound lanes on main arterials</small>
          </span>
        </label>
      </section>

      <div className="run-footer">
      <div className="run-row">
        <button className="run" onClick={onRun} disabled={loading}>
          {loading ? <span className="spinner" /> : '▶'} {loading ? 'Running…' : 'Run scenario'}
        </button>
        <button className="ghost" onClick={onReset} title="Reset to defaults">
          Reset
        </button>
      </div>
      <label className="toggle compact">
        <input type="checkbox" checked={autoRun} onChange={(e) => setAutoRun(e.target.checked)} />
        <span className="switch" />
        <span>Auto-run on change</span>
      </label>
      </div>
    </aside>
  )
}
