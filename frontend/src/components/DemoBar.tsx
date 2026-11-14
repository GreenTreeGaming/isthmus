import { useEffect } from 'react'
import type { DemoStep } from '../lib/demo'

interface Props {
  steps: DemoStep[]
  index: number
  onGo: (i: number) => void
  onExit: () => void
  loading: boolean
}

export function DemoBar({ steps, index, onGo, onExit, loading }: Props) {
  const step = steps[index]
  const last = index === steps.length - 1

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'Escape') onExit()
      else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        if (last) onExit()
        else onGo(index + 1)
      }
      else if (e.key === 'ArrowLeft' && index > 0) onGo(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, last, onGo, onExit])

  return (
    <aside className="panel demo-panel" role="dialog" aria-label="Guided demo">
      <div className="demo-top">
        <span className="demo-count">Guided demo · {index + 1} / {steps.length}</span>
        <button className="icon-btn" onClick={onExit} aria-label="Exit demo (Esc)" title="Exit demo (Esc)">
          ✕
        </button>
      </div>
      <div className="demo-steps">
        {steps.map((s, i) => (
          <button key={s.title} className={i === index ? 'on' : i < index ? 'done' : ''} onClick={() => onGo(i)} title={s.title} aria-label={`Step ${i + 1}: ${s.title}`}>
            <b>{i + 1}</b>
          </button>
        ))}
      </div>
      <h2 className="demo-title">
        {step.title}
        {loading && <span className="spinner sm" />}
      </h2>
      <p className="demo-caption">{step.caption}</p>
      {step.compareLabel && <p className="demo-compare">Cards show the change from: <b>{step.compareLabel}</b></p>}
      <div className="demo-actions">
        <button className="ghost" onClick={() => onGo(index - 1)} disabled={index === 0}>
          ← Back
        </button>
        <button className="run" onClick={() => (last ? onExit() : onGo(index + 1))}>
          {last ? 'Finish' : 'Next →'}
        </button>
      </div>
      <div className="demo-keys">← → to step · Esc to exit</div>
    </aside>
  )
}
