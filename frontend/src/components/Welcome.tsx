import { useEffect } from 'react'
import { COLORS, rgb } from '../lib/colors'

interface Props {
  onDemo: () => void
  onClose: () => void
  onHowItWorks: () => void
}

/** First-visit explainer: what Isthmus is, why it exists, how to read the map, how to use it. */
export function Welcome({ onDemo, onClose, onHowItWorks }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="welcome-backdrop" onClick={onClose}>
      <div className="welcome" role="dialog" aria-modal="true" aria-labelledby="welcome-title" onClick={(e) => e.stopPropagation()}>
        <button className="icon-btn welcome-close" onClick={onClose} aria-label="Close">✕</button>
        <div className="welcome-kicker">Isthmus · hazmat evacuation planner for downtown Madison</div>
        <h1 id="welcome-title">When a train derails downtown, who should run, and who should stay inside?</h1>
        <p className="welcome-lede">
          Downtown Madison sits on a strip of land about a kilometer wide between two lakes. Rail lines run straight
          through it, past the Capitol, hospitals and nursing homes, and only a handful of roads lead out. Place a
          chlorine or ammonia derailment on any rail line and, in about a second, Isthmus draws the official danger
          zone, decides <b>block by block who evacuates and who shelters in place</b>, staggers departures so the roads
          don't gridlock, and sends buses to residents without a car, each pickup timed <b>before the gas arrives</b>.
        </p>

        <div className="welcome-grid">
          <section>
            <h2>Why it matters</h2>
            <p className="muted">Most evacuation plans assume everyone has a car and everyone should leave. For a toxic gas, that's wrong twice:</p>
            <ul className="welcome-points">
              <li><b>Driving out can be more dangerous than staying in.</b> If the gas reaches a block before its residents could drive clear, they are safer indoors with the windows shut.</li>
              <li><b>Not everyone can leave on their own.</b> Households without a car, seniors and nursing-home residents need a ride, and that ride has a deadline: the moment the gas arrives.</li>
            </ul>
          </section>

          <section>
            <h2>How to read the map</h2>
            <ul className="welcome-legend">
              <li><span className="waves">{COLORS.waves.map((c, i) => <i key={i} style={{ background: rgb(c) }} />)}</span><span><b>Orange: evacuate</b>, in timed waves. The darkest orange leaves first.</span></li>
              <li><i className="sw" style={{ background: rgb(COLORS.shelter) }} /><span><b>Purple: shelter in place.</b> The gas would arrive before they could get out.</span></li>
              <li><i className="sw zone" /><span><b>Red circle and dashed square:</b> the official danger zone (DOT Emergency Response Guidebook).</span></li>
              <li><i className="line glow" /><span><b>Thick dashed roads:</b> choke points, where traffic backs up.</span></li>
              <li><i className="line bus" /><span><b>Blue dashed lines:</b> bus routes picking up residents who need a ride.</span></li>
            </ul>
          </section>
        </div>

        <section className="welcome-try">
          <h2>Try it</h2>
          <ol>
            <li><b>▶ Demo</b> walks through four scenarios in about a minute.</li>
            <li><b>Click a rail line</b> to move the derailment; change wind, time of day or buses on the left.</li>
            <li><b>Click any colored block or bus route</b> to see why it got its instruction.</li>
            <li><b>Press Play</b> on the timeline to watch the traffic simulation unfold.</li>
          </ol>
        </section>

        <p className="welcome-foot">
          A planning tool for "what if", not an alert system. Population comes from public, aggregated Census data; the map
          shows <b>areas with the most residents who need help</b>, never individuals.
        </p>
        <div className="welcome-actions">
          <button className="run big" onClick={onDemo}>▶ Start the guided demo</button>
          <button className="ghost big" onClick={onClose}>Explore on my own</button>
          <button className="link" onClick={onHowItWorks}>How does it work? →</button>
        </div>

      </div>
    </div>
  )
}
