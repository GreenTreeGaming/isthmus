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
    <div className="panel demo-bar" role="dialog" aria-label="Guided demo">
      <div className="demo-steps" aria-hidden>
        {steps.map((s, i) => (
          <button key={s.title} className={i === index ? 'on' : i < index ? 'done' : ''} onClick={() => onGo(i)} title={s.title}>
            {i + 1}
          </button>
        ))}
      </div>
      <div className="demo-text">
        <div className="demo-title">
          <span className="demo-count">Step {index + 1} of {steps.length}</span>
          {step.title}
          {loading && <span className="spinner sm" />}
        </div>
        <p>{step.caption}</p>
      </div>
      <div className="demo-actions">
        <button className="ghost" onClick={() => onGo(index - 1)} disabled={index === 0}>
          ← Back
        </button>
        <button className="run" onClick={() => (last ? onExit() : onGo(index + 1))}>
          {last ? 'Finish' : 'Next →'}
        </button>
        <button className="icon-btn" onClick={onExit} aria-label="Exit demo (Esc)" title="Exit demo (Esc)">
          ✕
        </button>
      </div>
    </div>
  )
}
