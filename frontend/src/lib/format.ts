const nf = new Intl.NumberFormat('en-US')

export const fmtInt = (n: number | null | undefined) => (n == null ? '—' : nf.format(Math.round(n)))

export function fmtCompact(n: number | null | undefined): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`
  return nf.format(Math.round(n))
}

/** 7380 -> "2h 03m"; 540 -> "9 min" */
export function fmtDuration(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '—'
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min`
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

/** Elapsed sim time as T+mm:ss / T+h:mm:ss */
export function fmtClock(s: number): string {
  const t = Math.max(0, Math.round(s))
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = t % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(sec).padStart(2, '0')
  return h ? `T+${h}:${mm}:${ss}` : `T+${mm}:${ss}`
}

export const fmtPct = (x: number) => `${Math.round(x * 100)}%`

export function compass(deg: number): string {
  const names = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return names[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16]
}
