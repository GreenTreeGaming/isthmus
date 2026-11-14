import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getAssumptions, getBlockFrequency, getBlocks, getRail, simulate } from './api'
import { ControlPanel } from './components/ControlPanel'
import { DemoBar } from './components/DemoBar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Toasts, type ToastMsg } from './components/Toast'
import { InfoCard, type Selection } from './components/InfoCard'
import { Legend } from './components/Legend'
import { MapView, type LayerToggles } from './components/MapView'
import { ScenarioStrip } from './components/ScenarioStrip'
import { SummaryCards, type Pinned } from './components/SummaryCards'
import { Timeline } from './components/Timeline'
import { CAPITOL, DEMO_STEPS } from './lib/demo'
import { derive } from './lib/derive'
import { DEFAULT_TIMING, type WaveTiming } from './lib/explain'
import { nearLandmark, nearestRailName, snapToRail } from './lib/geo'
import { AssumptionsTab } from './tabs/AssumptionsTab'
import { PlanningTab } from './tabs/PlanningTab'
import type { BlockFrequency, BlockGeoCollection, RailCollection, ScenarioParams } from './types'
import { DEFAULT_PARAMS, useScenario } from './useScenario'

type Tab = 'live' | 'planning' | 'assumptions'

const SOURCE_LABEL: Record<string, [string, string]> = {
  placeholder: ['Placeholder data', 'warn'],
  mock: ['Mock engine', 'warn'],
  real: ['Live engine', 'ok'],
}

const TOD_SHORT: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }
function shortLabel(p: ScenarioParams) {
  return `${TOD_SHORT[p.time_of_day]}, ${p.wind_speed_mps} m/s, ${p.bus_count} buses${p.contraflow ? ', contraflow' : ''}`
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

  // Errors surface as toasts; the map and last good result stay on screen.
  const [staticError, setStaticError] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set())
  const dismiss = useCallback((id: string) => setDismissed((d) => new Set(d).add(id)), [])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [timing, setTiming] = useState<WaveTiming>(DEFAULT_TIMING)
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
      .catch((e: Error) => {
        setPickHint('Rail lines unavailable — is the backend running?')
        setStaticError(`Could not load map data (${e.message}).`)
      })
    getBlocks()
      .then((r) => setBlockGeo(r.data))
      .catch((e: Error) => setStaticError(`Could not load census block outlines (${e.message}).`))
    getAssumptions()
      .then((r) => {
        const items = r.data.groups.flatMap((g) => g.items)
        const num = (k: string, d: number) => {
          const v = items.find((it) => it.key === k)?.value
          return typeof v === 'number' ? v : d
        }
        setTiming({ mobilization_s: num('MOBILIZATION_S', 300), wave_interval_s: num('WAVE_INTERVAL_S', 600) })
      })
      .catch(() => undefined)
    getBlockFrequency()
      .then((r) => {
        if (!r.data.length) return
        const map = new Map(r.data.map((f) => [f.block_id, f]))
        setFrequency({ map, max: Math.max(0.01, ...r.data.map((f) => f.share_shelter)) })
      })
      .catch(() => undefined)
  }, [setParams])

  // Compare: a pinned summary that later runs are measured against.
  const [pinned, setPinned] = useState<Pinned | null>(null)
  const compareSeq = useRef(0)

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
      // Steps with a baseline run it quietly and pin it, so the cards show what changed.
      const seq = ++compareSeq.current
      setPinned(null)
      if (step.compareTo) {
        const base: ScenarioParams = { ...DEFAULT_PARAMS, ...release, ...step.compareTo }
        simulate(base)
          .then((r) => {
            if (compareSeq.current === seq) setPinned({ summary: r.data.summary, label: step.compareLabel ?? 'Baseline' })
          })
          .catch(() => undefined)
      }
    },
    [rail, autoRun, run, setParams],
  )
  const exitDemo = useCallback(() => {
    compareSeq.current += 1
    setDemo(null)
    setPinned(null)
  }, [])

  // Fit the camera to the zone on the first result, and to each demo step's zone once it lands.
  const [fitFor, setFitFor] = useState<typeof result>(null)
  if (result && !loading && result !== fitFor && (demo != null || fitFor == null)) setFitFor(result)

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

  const railName = useMemo(() => (rail ? nearestRailName(rail, params.release_lon, params.release_lat) : null), [rail, params.release_lon, params.release_lat])
  const place = nearLandmark(params.release_lon, params.release_lat)

  const toasts = useMemo(() => {
    const out: ToastMsg[] = []
    if (error) out.push({ id: `sim:${error}`, title: 'Simulation failed', detail: error, action: { label: 'Retry', run: () => void run() } })
    if (staticError) out.push({ id: `static:${staticError}`, title: 'Backend unavailable', detail: `${staticError} Start it with: uvicorn backend.main:app --port 8000`, action: { label: 'Reload', run: () => window.location.reload() } })
    return out.filter((t) => !dismissed.has(t.id))
  }, [error, staticError, dismissed, run])

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
        <div className={`view live ${tab === 'live' ? '' : 'hidden'} ${loading ? 'is-loading' : ''} ${demo != null ? 'demo-mode' : ''}`}>
          <ErrorBoundary label="map">
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
            selection={selection}
            onSelect={setSelection}
            fitTo={fitFor?.zones ?? null}
            railOnly={demo != null}
          />
          </ErrorBoundary>
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
            railName={railName}
            place={place}
          />
          <div className="overlay-top">
            <ScenarioStrip params={params} railName={railName} place={place}>
              {pinned ? (
                <button className="chip pinned" onClick={() => setPinned(null)} title="Stop comparing">
                  vs. {pinned.label} <span aria-hidden>✕</span>
                </button>
              ) : (
                <button
                  className="chip"
                  disabled={!result || loading}
                  onClick={() => result && setPinned({ summary: result.summary, label: shortLabel(result.params) })}
                  title="Save this result; the next runs show what changed"
                >
                  📌 Pin result
                </button>
              )}
            </ScenarioStrip>
            <SummaryCards summary={result?.summary ?? null} loading={loading} pinned={pinned} />
          </div>
          {selection && result && (
            <InfoCard
              selection={selection}
              blocks={result.blocks}
              buses={result.buses}
              derived={derived}
              timing={timing}
              onClose={() => setSelection(null)}
              onHoverBus={setHoveredBus}
            />
          )}
          <Legend
            hidden={selection != null}
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
        {tab === 'planning' && (
          <div className="view">
            <ErrorBoundary label="planning view">
            <PlanningTab
              frequencyReady={frequency != null}
              onShowFrequency={() => {
                setToggles((t) => ({ ...t, frequency: true, blocks: true }))
                setSelection(null)
                setTab('live')
              }}
            />
            </ErrorBoundary>
          </div>
        )}
        {tab === 'assumptions' && <div className="view"><ErrorBoundary label="assumptions view"><AssumptionsTab /></ErrorBoundary></div>}
      </main>
      <Toasts toasts={toasts} dismiss={dismiss} />
    </div>
  )
}
