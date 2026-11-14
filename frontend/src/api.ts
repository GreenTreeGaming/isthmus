import type { Assumptions, Insights, RailCollection, ScenarioParams, ScenarioResponse } from './types'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface Sourced<T> {
  data: T
  source: string
}

async function request<T>(path: string, init?: RequestInit): Promise<Sourced<T>> {
  const res = await fetch(`${API_URL}${path}`, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return { data: (await res.json()) as T, source: res.headers.get('X-Isthmus-Source') ?? 'unknown' }
}

export const simulate = (params: ScenarioParams, signal?: AbortSignal) =>
  request<ScenarioResponse>('/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal,
  })

export const getRail = () => request<RailCollection>('/rail')
export const getInsights = () => request<Insights>('/insights')
export const getAssumptions = () => request<Assumptions>('/assumptions')
