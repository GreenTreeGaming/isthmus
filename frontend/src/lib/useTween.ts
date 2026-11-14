import { useEffect, useRef, useState } from 'react'

/** Animates a number toward `target` (ease-out), so card values count up/down instead of jumping. */
export function useTween(target: number | null, ms = 650): number | null {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    if (target == null) return
    const start = from.current ?? target
    if (start === target) {
      from.current = target
      return
    }
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms)
      const v = start + (target - start) * (1 - Math.pow(1 - k, 3))
      from.current = v
      setValue(v)
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return target == null ? null : (value ?? target)
}
