import { useEffect } from 'react'

export interface ToastMsg {
  id: string
  title: string
  detail: string
  action?: { label: string; run: () => void }
}

/** Error toasts, top-center. Each one auto-dismisses after 9 s. */
export function Toasts({ toasts, dismiss }: { toasts: ToastMsg[]; dismiss: (id: string) => void }) {
  useEffect(() => {
    if (!toasts.length) return
    const timers = toasts.map((t) => window.setTimeout(() => dismiss(t.id), 9000))
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [toasts, dismiss])
  if (!toasts.length) return null
  return (
    <div className="toasts" role="alert" aria-live="assertive">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          <span className="toast-icon" aria-hidden>!</span>
          <div className="toast-text">
            <b>{t.title}</b>
            <span>{t.detail}</span>
          </div>
          {t.action && (
            <button className="ghost sm" onClick={() => { t.action!.run(); dismiss(t.id) }}>
              {t.action.label}
            </button>
          )}
          <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss">✕</button>
        </div>
      ))}
    </div>
  )
}
