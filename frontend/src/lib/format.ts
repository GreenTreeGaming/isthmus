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

/** Elapsed time since the alert: "T+12 min" (or "T+1h 05m"). */
export function fmtClock(s: number): string {
  const m = Math.max(0, Math.round(s / 60))
  return m < 60 ? `T+${m} min` : `T+${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

export const fmtPct = (x: number) => `${Math.round(x * 100)}%`

export function compass(deg: number): string {
  const names = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return names[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16]
}

/** Spoken-style span for sentences: 540 -> "9 min", 11400 -> "3 h 10 min", 7200 -> "2 h". */
export function fmtSpan(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '—'
  const m = Math.max(0, Math.round(s / 60))
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`
}
