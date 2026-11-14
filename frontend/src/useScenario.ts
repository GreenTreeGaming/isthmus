import { useCallback, useEffect, useRef, useState } from 'react'
import { simulate } from './api'
import type { ScenarioParams, ScenarioResponse } from './types'

// Demo defaults: chlorine, large spill, 1.5 m/s wind from 225° (SW), daytime.
export const DEFAULT_PARAMS: ScenarioParams = {
  release_lon: -89.3705,
  release_lat: 43.079,
  chemical: 'chlorine',
  spill_size: 'large',
  wind_from_deg: 225,
  wind_speed_mps: 1.5,
  time_of_day: 'day',
  compliance: 0.85,
  bus_count: 20,
  bus_capacity: 60,
  contraflow: false,
  closed_edge_ids: [],
}

const DEBOUNCE_MS = 450

export function useScenario() {
  const [params, setParams] = useState<ScenarioParams>(DEFAULT_PARAMS)
  const [result, setResult] = useState<ScenarioResponse | null>(null)
  const [source, setSource] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRun, setAutoRun] = useState(true)
  const abortRef = useRef<AbortController | null>(null)
  const paramsRef = useRef(params)

  useEffect(() => {
    paramsRef.current = params
  }, [params])

  const run = useCallback(async (p?: ScenarioParams) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    setError(null)
    try {
      const { data, source } = await simulate(p ?? paramsRef.current, ctrl.signal)
      if (ctrl.signal.aborted) return
      setResult(data)
      setSource(source)
    } catch (e) {
      if (ctrl.signal.aborted || (e as Error).name === 'AbortError') return
      setError((e as Error).message.includes('fetch') ? 'Cannot reach the API. Is the backend running on port 8000?' : (e as Error).message)
    } finally {
      if (abortRef.current === ctrl) setLoading(false)
    }
  }, [])

  // Debounced auto-rerun whenever params change.
  useEffect(() => {
    if (!autoRun) return
    const id = window.setTimeout(() => void run(params), result ? DEBOUNCE_MS : 0)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `result` only picks the first-run delay
  }, [params, autoRun, run])

  const update = useCallback(<K extends keyof ScenarioParams>(key: K, value: ScenarioParams[K]) => {
    setParams((p) => ({ ...p, [key]: value }))
  }, [])

  return { params, setParams, update, result, source, loading, error, run, autoRun, setAutoRun }
}
