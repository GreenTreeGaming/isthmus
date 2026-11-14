import { useCallback, useEffect, useMemo, useState } from 'react'
import { getBlockFrequency, getBlocks, getRail } from './api'
import { ControlPanel } from './components/ControlPanel'
import { DemoBar } from './components/DemoBar'
import { Legend } from './components/Legend'
import { MapView, type LayerToggles } from './components/MapView'
import { SummaryCards } from './components/SummaryCards'
import { Timeline } from './components/Timeline'
import { CAPITOL, DEMO_STEPS } from './lib/demo'
import { derive } from './lib/derive'
import { snapToRail } from './lib/geo'
import { AssumptionsTab } from './tabs/AssumptionsTab'
import { PlanningTab } from './tabs/PlanningTab'
import type { BlockFrequency, BlockGeoCollection, RailCollection } from './types'
import { DEFAULT_PARAMS, useScenario } from './useScenario'

type Tab = 'live' | 'planning' | 'assumptions'

const SOURCE_LABEL: Record<string, [string, string]> = {
  placeholder: ['Placeholder data', 'warn'],
  mock: ['Mock engine', 'warn'],
  real: ['Live engine', 'ok'],
}

export default function App() {
  const [tab, setTab] = useState<Tab>('live')
  const { params, setParams, update, result, source, loading, error, run, autoRun, setAutoRun } = useScenario()
  const [rail, setRail] = useState<RailCollection | null>(null)
  const [pickHint, setPickHint] = useState<string | null>(null)
  const [toggles, setToggles] = useState<LayerToggles>({ blocks: true, heatmap: false, roads: true, traffic: true, buses: true, frequency: false })
  const [time, setTime] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [hoveredBus, setHoveredBus] = useState<number | null>(null)

  const [blockGeo, setBlockGeo] = useState<BlockGeoCollection | null>(null)
  const [frequency, setFrequency] = useState<{ map: Map<string, BlockFrequency>; max: number } | null>(null)

  // Static data, fetched once: rail lines, block outlines (/simulate only sends per-run block properties),
  // and the batch "how often told to shelter" table.
  useEffect(() => {
    getRail()
      .then((r) => {
        setRail(r.data)
        // Make sure the starting pin sits on a rail line too.
        setParams((p) => {
          const snap = snapToRail(r.data, p.release_lon, p.release_lat)
          return snap && snap[2] > 1 ? { ...p, release_lon: +snap[0].toFixed(6), release_lat: +snap[1].toFixed(6) } : p
        })
      })
      .catch(() => setPickHint('Rail lines unavailable — is the backend running?'))
    getBlocks()
      .then((r) => setBlockGeo(r.data))
      .catch(() => undefined) // surfaced via the simulate error banner
    getBlockFrequency()
      .then((r) => {
        if (!r.data.length) return
        const map = new Map(r.data.map((f) => [f.block_id, f]))
        setFrequency({ map, max: Math.max(0.01, ...r.data.map((f) => f.share_shelter)) })
      })
      .catch(() => undefined)
  }, [setParams])

  // Guided demo: each step sets the controls from defaults and reruns.
  const [demo, setDemo] = useState<number | null>(null)
  const goDemo = useCallback(
    (i: number) => {
      const step = DEMO_STEPS[i]
      if (!step) return
      const snap = rail ? snapToRail(rail, CAPITOL[0], CAPITOL[1]) : null
      const release = snap ? { release_lon: +snap[0].toFixed(6), release_lat: +snap[1].toFixed(6) } : { release_lon: -89.381496, release_lat: 43.07134 }
      const p = { ...DEFAULT_PARAMS, ...release, ...step.params }
      setTab('live')
      setDemo(i)
      setPlaying(false)
      setTime(null)
      setParams(p)
      if (!autoRun) void run(p)
    },
    [rail, autoRun, run, setParams],
  )
  const exitDemo = useCallback(() => setDemo(null), [])

  const derived = useMemo(() => (result && blockGeo ? derive(result, blockGeo) : null), [result, blockGeo])

  // A new result may be shorter than the current timeline position.
  const timeInRange = time != null && derived ? Math.min(time, derived.duration_s) : time

  const onPickRelease = useCallback(
    (lon: number, lat: number) => {
      if (!rail) return
      // Derailments only happen on track: always snap to the nearest rail line.
      const snap = snapToRail(rail, lon, lat)
      if (!snap) return
      setPickHint(snap[2] > 150 ? 'Snapped to the nearest rail line.' : null)
      setParams((p) => ({ ...p, release_lon: +snap[0].toFixed(6), release_lat: +snap[1].toFixed(6) }))
    },
    [rail, setParams],
  )

  useEffect(() => {
    if (!pickHint || !rail) return
    const id = window.setTimeout(() => setPickHint(null), 4000)
    return () => window.clearTimeout(id)
  }, [pickHint, rail])

  const [srcLabel, srcTone] = SOURCE_LABEL[source] ?? ['', '']

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden>
            <rect width="32" height="32" rx="7" fill="#151c26" />
            <path d="M4 22c6-1 9-5 12-9s6-6 12-7" stroke="#ff8a1f" strokeWidth="3" fill="none" strokeLinecap="round" />
            <circle cx="16" cy="13" r="3.2" fill="#ef4444" />
          </svg>
          <div>
            <div className="brand-name">Isthmus</div>
            <div className="brand-sub">Hazmat evacuation planner · Downtown Madison</div>
          </div>
        </div>
        <nav className="tabs" role="tablist">
          {(
            [
              ['live', 'Live scenario'],
              ['planning', 'Planning'],
              ['assumptions', 'Assumptions'],
            ] as [Tab, string][]
          ).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </nav>
        <button className={`demo-btn ${demo != null ? 'on' : ''}`} onClick={() => (demo == null ? goDemo(0) : exitDemo())}>
          {demo == null ? '▶ Demo' : '■ Exit demo'}
        </button>
        <div className="status">
          {tab === 'live' && srcLabel && <span className={`badge ${srcTone}`}>{srcLabel}</span>}
          {tab === 'live' && loading && <span className="badge"><span className="spinner sm" /> Simulating</span>}
        </div>
        {loading && <div className="progress" />}
      </header>

      <main className="main">
        <div className={`view live ${tab === 'live' ? '' : 'hidden'} ${loading ? 'is-loading' : ''}`}>
          <MapView
            result={result}
            derived={derived}
            rail={rail}
            params={params}
            toggles={toggles}
            time={timeInRange}
            onPickRelease={onPickRelease}
            hoveredBus={hoveredBus}
            setHoveredBus={setHoveredBus}
            blockGeo={blockGeo}
            frequency={frequency?.map ?? null}
            frequencyMax={frequency?.max ?? 1}
          />
          {loading && (
            <div className="sim-overlay" role="status" aria-live="polite">
              <span className="spinner" /> Simulating scenario…
            </div>
          )}
          <ControlPanel
            params={params}
            update={update}
            onRun={() => void run()}
            onReset={() => setParams(DEFAULT_PARAMS)}
            loading={loading}
            autoRun={autoRun}
            setAutoRun={setAutoRun}
            pickHint={pickHint}
          />
          <div className="overlay-top">
            <SummaryCards summary={result?.summary ?? null} loading={loading} />
            {error && (
              <div className="error-box" role="alert">
                <b>Simulation failed.</b> {error}
                <button className="ghost sm" onClick={() => void run()}>Retry</button>
              </div>
            )}
          </div>
          <Legend
            toggles={toggles}
            setToggle={(k, v) => setToggles((t) => ({ ...t, [k]: v }))}
            frequencyMax={frequency ? frequency.max : null}
          />
          {demo != null && <DemoBar steps={DEMO_STEPS} index={demo} onGo={goDemo} onExit={exitDemo} loading={loading} />}
          {derived && (
            <Timeline
              time={timeInRange}
              setTime={setTime}
              duration={derived.duration_s}
              playing={playing}
              setPlaying={setPlaying}
              clearance={result ? result.summary.sim_clearance_s || result.summary.clearance_time_s : null}
            />
          )}
        </div>
        {tab === 'planning' && <div className="view"><PlanningTab /></div>}
        {tab === 'assumptions' && <div className="view"><AssumptionsTab /></div>}
      </main>
    </div>
  )
}
