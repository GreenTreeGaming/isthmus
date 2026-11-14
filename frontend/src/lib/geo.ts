import type { Position } from 'geojson'
import type { RailCollection } from '../types'

const M_PER_DEG_LAT = 110_540
const mPerDegLon = (lat: number) => 111_320 * Math.cos((lat * Math.PI) / 180)

/** Snap a clicked point to the nearest point on any rail line. Returns [lon, lat, distance_m]. */
export function snapToRail(rail: RailCollection, lon: number, lat: number): [number, number, number] | null {
  const kx = mPerDegLon(lat)
  let best: [number, number, number] | null = null
  for (const f of rail.features) {
    const cs = f.geometry.coordinates
    for (let i = 0; i < cs.length - 1; i++) {
      const ax = (cs[i][0] - lon) * kx
      const ay = (cs[i][1] - lat) * M_PER_DEG_LAT
      const bx = (cs[i + 1][0] - lon) * kx
      const by = (cs[i + 1][1] - lat) * M_PER_DEG_LAT
      const dx = bx - ax
      const dy = by - ay
      const len2 = dx * dx + dy * dy || 1
      const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2))
      const px = ax + t * dx
      const py = ay + t * dy
      const d = Math.hypot(px, py)
      if (!best || d < best[2]) best = [lon + px / kx, lat + py / M_PER_DEG_LAT, d]
    }
  }
  return best
}

export function centroid(ring: Position[]): [number, number] {
  let x = 0
  let y = 0
  const n = ring.length > 1 && ring[0][0] === ring.at(-1)![0] && ring[0][1] === ring.at(-1)![1] ? ring.length - 1 : ring.length
  for (let i = 0; i < n; i++) {
    x += ring[i][0]
    y += ring[i][1]
  }
  return [x / n, y / n]
}

export function distM(a: Position, b: Position): number {
  return Math.hypot((a[0] - b[0]) * mPerDegLon(a[1]), (a[1] - b[1]) * M_PER_DEG_LAT)
}

/** Point at fraction f (0..1) along a polyline, by length. */
export function along(path: Position[], f: number): [number, number] {
  if (path.length === 1) return [path[0][0], path[0][1]]
  const seg: number[] = []
  let total = 0
  for (let i = 0; i < path.length - 1; i++) {
    const d = distM(path[i], path[i + 1])
    seg.push(d)
    total += d
  }
  let target = Math.max(0, Math.min(1, f)) * total
  for (let i = 0; i < seg.length; i++) {
    if (target <= seg[i] || i === seg.length - 1) {
      const t = seg[i] ? Math.min(1, target / seg[i]) : 0
      return [path[i][0] + (path[i + 1][0] - path[i][0]) * t, path[i][1] + (path[i + 1][1] - path[i][1]) * t]
    }
    target -= seg[i]
  }
  const last = path[path.length - 1]
  return [last[0], last[1]]
}
