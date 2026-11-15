import { useState } from 'react'
import { createPortal } from 'react-dom'

/** Small "i" button with an explanation bubble (hover or keyboard focus). Fixed-position so panels can't clip it. */
export function Tip({ text, label = 'More info' }: { text: string; label?: string }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const show = (e: React.SyntheticEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setAt({ x: Math.min(r.left, window.innerWidth - 330), y: r.bottom + 8 })
  }
  return (
    <span className="tip-wrap">
      <button
        type="button"
        className="tip"
        aria-label={label}
        onMouseEnter={show}
        onMouseLeave={() => setAt(null)}
        onFocus={show}
        onBlur={() => setAt(null)}
        onClick={(e) => e.stopPropagation()}
      >
        i
      </button>
      {at &&
        createPortal(
          <span className="tip-bubble" role="tooltip" style={{ left: Math.max(8, at.x), top: at.y }}>
            {text}
          </span>,
          document.body,
        )}
    </span>
  )
}
