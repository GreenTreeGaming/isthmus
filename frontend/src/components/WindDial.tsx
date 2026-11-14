import { useRef } from 'react'
import { compass } from '../lib/format'

interface Props {
  fromDeg: number
  onChange: (deg: number) => void
}

const SIZE = 112
const C = SIZE / 2
const R = 44

/** Compass dial. The arrow points where the wind blows TO; the value is where it comes FROM (meteorological). */
export function WindDial({ fromDeg, onChange }: Props) {
  const ref = useRef<SVGSVGElement>(null)

  const setFromEvent = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect()
    const dx = e.clientX - (r.left + r.width / 2)
    const dy = e.clientY - (r.top + r.height / 2)
    // Pointer marks the FROM direction (where the wind originates).
    const deg = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360
    onChange(Math.round(deg / 5) * 5 % 360)
  }

  const toRad = (((fromDeg + 180) % 360) * Math.PI) / 180
  const fromRad = (fromDeg * Math.PI) / 180
  const tip = [C + Math.sin(toRad) * (R - 8), C - Math.cos(toRad) * (R - 8)]
  const tail = [C + Math.sin(fromRad) * (R - 4), C - Math.cos(fromRad) * (R - 4)]

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') onChange((fromDeg + 5) % 360)
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') onChange((fromDeg + 355) % 360)
  }

  return (
    <div className="wind-dial">
      <svg
        ref={ref}
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="slider"
        tabIndex={0}
        aria-label="Wind direction (from)"
        aria-valuenow={fromDeg}
        aria-valuemin={0}
        aria-valuemax={359}
        onKeyDown={onKey}
        onPointerDown={(e) => {
          ;(e.target as Element).setPointerCapture?.(e.pointerId)
          setFromEvent(e)
        }}
        onPointerMove={(e) => e.buttons === 1 && setFromEvent(e)}
      >
        <circle cx={C} cy={C} r={R + 6} className="dial-ring" />
        {Array.from({ length: 36 }, (_, i) => {
          const a = (i * 10 * Math.PI) / 180
          const long = i % 9 === 0
          const r1 = R + 6 - (long ? 8 : 4)
          return (
            <line key={i} x1={C + Math.sin(a) * r1} y1={C - Math.cos(a) * r1} x2={C + Math.sin(a) * (R + 5)} y2={C - Math.cos(a) * (R + 5)} className={long ? 'tick major' : 'tick'} />
          )
        })}
        {(['N', 'E', 'S', 'W'] as const).map((l, i) => {
          const a = (i * 90 * Math.PI) / 180
          return (
            <text key={l} x={C + Math.sin(a) * (R - 12)} y={C - Math.cos(a) * (R - 12) + 4} className="dial-label">
              {l}
            </text>
          )
        })}
        <line x1={tail[0]} y1={tail[1]} x2={tip[0]} y2={tip[1]} className="dial-arrow" markerEnd="url(#arrowhead)" />
        <circle cx={tail[0]} cy={tail[1]} r={5} className="dial-handle" />
        <defs>
          <marker id="arrowhead" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#7dd3fc" />
          </marker>
        </defs>
      </svg>
      <div className="wind-readout">
        <div className="big">{compass(fromDeg)}</div>
        <div className="muted">from {Math.round(fromDeg)}°</div>
        <div className="muted small">blowing toward {compass(fromDeg + 180)}</div>
      </div>
    </div>
  )
}
