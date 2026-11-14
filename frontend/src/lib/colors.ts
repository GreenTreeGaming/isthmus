import type { BlockProps } from '../types'

export type RGBA = [number, number, number, number]

export const COLORS = {
  shelter: [139, 92, 246] as const, // purple
  waves: [
    [255, 107, 26], // wave 0 — most urgent, most saturated
    [255, 146, 56],
    [255, 182, 102],
    [255, 212, 156],
  ] as const,
  outside: [96, 108, 124] as const,
  zone: [239, 68, 68] as const,
  rail: [168, 178, 196] as const,
  bus: [57, 135, 229] as const,
  onTime: [52, 199, 120] as const,
  late: [255, 84, 84] as const,
}

export function blockColor(p: BlockProps, alpha = 150): RGBA {
  if (p.decision === 'shelter') return [...COLORS.shelter, alpha]
  if (p.decision === 'evacuate') {
    const w = Math.min(Math.max(p.wave ?? 0, 0), COLORS.waves.length - 1)
    return [...COLORS.waves[w], alpha]
  }
  return [...COLORS.outside, Math.round(alpha * 0.28)]
}

// Road load: green (free) -> yellow (at capacity) -> red (over capacity).
const STOPS: [number, [number, number, number]][] = [
  [0.0, [46, 204, 113]],
  [0.6, [163, 214, 64]],
  [0.9, [250, 204, 21]],
  [1.15, [249, 115, 22]],
  [1.4, [239, 50, 50]],
]

export function loadColor(ratio: number, alpha = 235): RGBA {
  const r = Math.max(0, ratio)
  if (r <= STOPS[0][0]) return [...STOPS[0][1], alpha]
  for (let i = 1; i < STOPS.length; i++) {
    const [x1, c1] = STOPS[i]
    const [x0, c0] = STOPS[i - 1]
    if (r <= x1) {
      const t = (r - x0) / (x1 - x0)
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
        alpha,
      ]
    }
  }
  return [...STOPS[STOPS.length - 1][1], alpha]
}

export const LOAD_GRADIENT_CSS = `linear-gradient(90deg, ${STOPS.map(
  ([x, c]) => `rgb(${c.join(',')}) ${Math.round((x / 1.4) * 100)}%`,
).join(', ')})`

/** Sequential purple for "how often this block is told to shelter" (0..1). */
export function frequencyColor(share: number): RGBA {
  const t = Math.max(0, Math.min(1, share))
  if (t === 0) return [60, 66, 80, 30]
  const lo = [76, 52, 150]
  const hi = [216, 196, 255]
  return [
    Math.round(lo[0] + (hi[0] - lo[0]) * t),
    Math.round(lo[1] + (hi[1] - lo[1]) * t),
    Math.round(lo[2] + (hi[2] - lo[2]) * t),
    Math.round(90 + 150 * t),
  ]
}

export const FREQUENCY_GRADIENT_CSS = `linear-gradient(90deg, rgba(76,52,150,0.4), rgb(216,196,255))`

export const rgb = (c: readonly number[], a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`
