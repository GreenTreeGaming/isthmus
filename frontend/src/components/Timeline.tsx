import { useEffect, useRef } from 'react'
import { fmtClock } from '../lib/format'

interface Props {
  time: number | null
  setTime: (t: number | null) => void
  duration: number
  playing: boolean
  setPlaying: (p: boolean) => void
  clearance: number | null
}

const PLAYBACK_SECONDS = 24 // whole evacuation plays in ~24 s

export function Timeline({ time, setTime, duration, playing, setPlaying, clearance }: Props) {
  const last = useRef<number | null>(null)
  const timeRef = useRef(time)
  useEffect(() => {
    timeRef.current = time
  }, [time])

  useEffect(() => {
    if (!playing) return
    let raf = 0
    const tick = (now: number) => {
      const dt = last.current == null ? 0 : (now - last.current) / 1000
      last.current = now
      const next = (timeRef.current ?? 0) + (dt * duration) / PLAYBACK_SECONDS
      if (next >= duration) {
        setTime(duration)
        setPlaying(false)
        return
      }
      setTime(next)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      last.current = null
    }
  }, [playing, duration, setTime, setPlaying])

  const toggle = () => {
    if (!playing && (time == null || time >= duration)) setTime(0)
    setPlaying(!playing)
  }

  const t = time ?? duration
  const pct = (t / duration) * 100
  const clearPct = clearance ? Math.min(100, (clearance / duration) * 100) : null

  const tickStep = duration > 7200 ? 1800 : duration > 3600 ? 900 : 600
  const ticks: number[] = []
  for (let x = 0; x <= duration; x += tickStep) ticks.push(x)

  return (
    <div className={`panel timeline ${playing ? 'is-playing' : ''}`}>
      <button className="play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play the evacuation'}>
        {playing ? (
          <svg viewBox="0 0 16 16" width="18" height="18"><rect x="3" y="2" width="3.5" height="12" rx="1" fill="currentColor" /><rect x="9.5" y="2" width="3.5" height="12" rx="1" fill="currentColor" /></svg>
        ) : (
          <svg viewBox="0 0 16 16" width="18" height="18"><path d="M4 2.5v11a.8.8 0 0 0 1.2.7l9-5.5a.8.8 0 0 0 0-1.4l-9-5.5A.8.8 0 0 0 4 2.5z" fill="currentColor" /></svg>
        )}
        <span>{playing ? 'Pause' : time == null || time >= duration ? 'Play' : 'Resume'}</span>
      </button>
      <div className="clock">
        <div className="clock-value mono">{time == null ? 'Peak' : fmtClock(time)}</div>
        <div className="clock-sub">{time == null ? 'peak road load' : 'since the alert'}</div>
      </div>
      <div className="scrub">
        <input
          type="range"
          min={0}
          max={duration}
          step={1}
          value={t}
          aria-label="Simulation time"
          onChange={(e) => {
            setPlaying(false)
            setTime(Number(e.target.value))
          }}
          style={{ '--pct': `${pct}%` } as React.CSSProperties}
        />
        {clearPct != null && (
          <div className="clear-mark" style={{ left: `${clearPct}%` }} title="All evacuating vehicles out">
            <span>all out</span>
          </div>
        )}
        <div className="ticks" aria-hidden>
          {ticks.map((x) => (
            <span key={x} style={{ left: `${(x / duration) * 100}%` }}>{Math.round(x / 60)}′</span>
          ))}
        </div>
      </div>
      <button className={`chip ${time == null ? 'on' : ''}`} onClick={() => { setPlaying(false); setTime(null) }} title="Show peak load on every road">
        Peak
      </button>
    </div>
  )
}
