// Plain-language version of the README's "How it works", "Responsible use" and "Known limits".
// Static numbers come from README.md (data build + 576-scenario Databricks run).

interface Props {
  onGo: (tab: 'live' | 'planning' | 'assumptions') => void
  onDemo: () => void
}

const SOURCES: [string, string][] = [
  ['OpenStreetMap', 'Roads, rail lines, bus stops, hospitals'],
  ['2020 Census blocks', 'Who is home at night'],
  ['ACS 2022', 'Households without a car, age 65+, disability'],
  ['LEHD LODES 2022', 'Who is downtown during the day (workers)'],
  ['CMS', 'Nursing-home residents per day'],
  ['DOT Emergency Response Guidebook 2024', 'Danger-zone distances by chemical, spill and wind'],
  ['USGS 3DEP elevation', 'Ground height every 20 m, for floods'],
]

const STEPS: { title: string; body: string; see: string }[] = [
  {
    title: 'Draw the danger zone',
    body: 'The guidebook gives an isolation circle around the derailment plus a downwind protective-action area. Gas arrival at any point is its distance divided by wind speed.',
    see: 'Red circle and dashed square',
  },
  {
    title: 'Set the road rules',
    body: 'Inside the zone, roads stay open but only for driving away from the release. Nobody is routed into the zone.',
    see: 'Roads inside the square',
  },
  {
    title: 'Evacuate or shelter?',
    body: 'A block evacuates only if 5 minutes of warning plus its drive to safety (with a 1.5× congestion margin) beats the gas. Otherwise it is told to stay indoors.',
    see: 'Orange vs. purple blocks · click one for "Why?"',
  },
  {
    title: 'Fastest possible clearance',
    body: 'A max-flow search finds the shortest time the road network could carry every car out, and names the roads that limit it. Min-cost flow picks the routes.',
    see: '"Everyone out in" card',
  },
  {
    title: 'Departure waves',
    body: 'Blocks the gas reaches first leave first, in 10-minute waves that each fit through every exit and bottleneck, so the roads don’t gridlock.',
    see: 'Shades of orange (darker = earlier)',
  },
  {
    title: 'Traffic simulation',
    body: 'Cars move in 30-second steps; a road that is full makes them queue. This shows where and when roads back up.',
    see: 'Road colors, moving dots, Play button',
  },
  {
    title: 'Bus pickups with deadlines',
    body: 'Buses leave Madison Metro’s garage and pick up residents who need a ride. Every pickup is scheduled before the gas reaches that stop; anyone no bus can reach in time is counted as left behind.',
    see: 'Blue dashed routes · click one for its stop times',
  },
]

const LIMITS = [
  'Not a plume model: zones follow guidebook distances; terrain, buildings and lake breezes are ignored.',
  'Simplified traffic: queues without signals, turns or crashes. Good for ranking roads, not exact minutes.',
  'In light wind the official zone (6–7+ miles for a chlorine tank car) is longer than the study area; the map edge is treated as safe.',
  'Assisted-living facilities are not in the federal nursing-home list, and students are missing from daytime worker data.',
  'Each bus makes one trip. Shelters are large public buildings we chose, not official city designations.',
  "Floods use a 'bathtub' model of lake level — no rainfall runoff, storm sewers or river flow speed.",
]

export function HowItWorksTab({ onGo, onDemo }: Props) {
  return (
    <div className="page how">
      <header className="how-hero">
        <div className="welcome-kicker">How it works</div>
        <h2>From public data to a block-by-block plan in about a second</h2>
        <p>
          Isthmus answers one question for any derailment on Madison&apos;s isthmus: <b>should each block leave, or stay
          inside?</b> Then it plans the leaving (waves and routes) and the people who can&apos;t leave alone (buses with
          deadlines), and repeats it for 576 scenarios to find what holds every time.
        </p>
        <div className="how-cta">
          <button className="run" onClick={onDemo}>▶ See it in the guided demo</button>
          <button className="ghost" onClick={() => onGo('live')}>Open the live map</button>
        </div>
      </header>

      <section className="how-section">
        <div className="how-num">1</div>
        <div className="how-body">
          <h3>Build Madison from real public data</h3>
          <div className="source-grid">
            {SOURCES.map(([name, what]) => (
              <div key={name} className="source"><b>{name}</b><span>{what}</span></div>
            ))}
          </div>
          <div className="stat-row">
            <div><b>5,441</b><span>intersections</span></div>
            <div><b>13,909</b><span>road segments</span></div>
            <div><b>2,113</b><span>Census blocks</span></div>
            <div><b>200,853</b><span>residents</span></div>
          </div>
          <p className="muted small-note">
            Everything is counted per Census block, so the plan talks about areas, never individuals. One fix along the way: the
            jobs data put ~22,000 UW–Madison jobs on a single block, so daytime density is capped at 100,000 people/km².
          </p>
        </div>
      </section>

      <section className="how-section">
        <div className="how-num">2</div>
        <div className="how-body">
          <h3>Plan one scenario: seven steps</h3>
          <ol className="pipeline">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <div className="pipe-n">{i + 1}</div>
                <div>
                  <b>{s.title}</b>
                  <p>{s.body}</p>
                  <span className="pipe-see">On the map: {s.see}</span>
                </div>
              </li>
            ))}
          </ol>
          <div className="callout">
            <b>The hard part: rates vs. counts.</b> Road capacity is a rate (cars per hour), but evacuees are a count (cars).
            So for a guessed time <i>T</i>, each road can carry capacity × <i>T</i> cars, and a max-flow solver checks whether
            every car reaches an exit. A binary search over <i>T</i> finds the fastest possible clearance.
          </div>
        </div>
      </section>

      <section className="how-section">
        <div className="how-num">3</div>
        <div className="how-body">
          <h3>Floods: when the lakes rise</h3>
          <p>
            The same planner also handles a flood: Lake Mendota and/or Lake Monona (with the Yahara River below it) rise by a
            set height over a set number of hours. Only the first step changes; the waves, traffic simulation and bus routing
            after it are exactly the same.
          </p>
          <ul className="limits">
            <li><b>Ground height.</b> USGS 3DEP elevation, sampled every 20 m across the study area.</li>
            <li><b>Where water can actually go.</b> A priority-flood algorithm finds, for every 20 m cell, how far a lake must rise before water can flow there. It has to connect to the lake: a low spot behind high ground stays dry.</li>
            <li><b>Danger zone and arrival time.</b> Cells reached at the peak rise are the danger zone. The lake rises steadily, so water reaches a cell when the lake level passes that cell&apos;s height.</li>
            <li><b>Roads.</b> Flooded roads close, and &quot;away from the danger&quot; means toward higher ground.</li>
          </ul>
          <p className="muted small-note">On the map: light blue water spreading over time (press Play), the dashed outline of the peak flood, and the rising lake in a stronger blue.</p>
        </div>
      </section>

      <section className="how-section">
        <div className="how-num">4</div>
        <div className="how-body">
          <h3>Run everything: 576 scenarios on Databricks</h3>
          <div className="grid-eq">
            <span><b>8</b> derailment points</span>×<span><b>8</b> wind directions</span>×<span><b>3</b> wind speeds</span>×
            <span><b>3</b> times of day</span>=<span className="eq"><b>576</b> scenarios</span>
          </div>
          <p>
            The same engine runs on Databricks serverless compute, about 1 second per scenario with 0 failures. Results land in
            Delta tables behind a dashboard and a Genie space you can ask questions in plain English, and in the{' '}
            <button className="link inline" onClick={() => onGo('planning')}>Planning tab</button>.
          </p>
        </div>
      </section>

      <div className="how-two">
        <section className="assume-card">
          <h3>Responsible use</h3>
          <ul className="limits">
            <li><b>A planning tool, not an alert system.</b> It is for exploring &quot;what if&quot; ahead of time, not for instructions during a real incident.</li>
            <li><b>Areas, never individuals.</b> Public, aggregated Census tables only; the map shows areas with the most residents who need help.</li>
            <li><b>Nothing hidden.</b> Every number the model uses is in the <button className="link inline" onClick={() => onGo('assumptions')}>Assumptions tab</button>, and every decision has a reason.</li>
          </ul>
        </section>
        <section className="assume-card">
          <h3>Known limits</h3>
          <ul className="limits">
            {LIMITS.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </section>
      </div>
    </div>
  )
}
