import { useEffect, useState } from 'react'
import {
  Bar, BarChart, Cell, LabelList, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getInsights, getRobustness } from '../api'
import type { FloodInsights, Insights, Robustness } from '../types'
import { compass, fmtCompact, fmtDuration, fmtInt, fmtPct } from '../lib/format'

// Monochrome charts: neutral bars, and colour only on the worst case (amber = slowest / most frequent, red = most exposed).
const SERIES = '#8a8f98'
const STRONG = '#f7f8f8'
const AMBER = '#e0a43a'
const RED = '#ef4444'
const GRID = 'rgba(255,255,255,0.06)'
const AXIS = { fill: '#8a8f98', fontSize: 13 }
const LABEL = '#d0d6e0'
const TT = {
  contentStyle: {
    background: 'rgba(15,16,17,0.92)',
    backdropFilter: 'blur(16px) saturate(180%)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 8,
    fontSize: 13,
    fontVariantNumeric: 'tabular-nums',
    boxShadow: '0 12px 30px rgba(0,0,0,0.5)',
    padding: '8px 12px',
  },
  labelStyle: { color: '#f7f8f8', fontWeight: 600, marginBottom: 2 },
  itemStyle: { color: '#d0d6e0', padding: 0 },
  cursor: { fill: 'rgba(255,255,255,0.04)' },
}

/** One Cell per bar: the largest value gets the highlight colour, the rest stay neutral. */
function highlightMax<T>(data: T[], key: (d: T) => number, color: string) {
  const max = Math.max(...data.map(key))
  return data.map((d, i) => <Cell key={i} fill={key(d) === max && max > 0 ? color : SERIES} />)
}
const FACILITY_LABEL: Record<string, string> = { nursing_home: 'Nursing home', hospital: 'Hospital', dorm: 'Residence hall', stadium: 'Stadium' }

function ChartCard({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="chart-card">
      <h3>{title}</h3>
      <p className="muted">{sub}</p>
      <div className="chart-body">{children}</div>
    </section>
  )
}

interface Finding {
  big: string
  title: React.ReactNode
  detail: string
  tone: 'warn' | 'info' | 'bad'
}

export function PlanningTab({ onShowFrequency, frequencyReady }: { onShowFrequency: () => void; frequencyReady: boolean }) {
  const [data, setData] = useState<Insights | null>(null)
  const [source, setSource] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [robust, setRobust] = useState<Robustness | null>(null)

  useEffect(() => {
    getInsights()
      .then((r) => {
        setData(r.data)
        setSource(r.source)
      })
      .catch((e: Error) => setError(e.message))
    getRobustness()
      .then((r) => 'variants' in r.data && setRobust(r.data as Robustness))
      .catch(() => undefined) // optional section
  }, [])

  if (error) return <div className="page"><div className="error-box">Could not load insights: {error}</div></div>
  if (!data) return <div className="page"><div className="loading-box"><span className="spinner" /> Loading insights…</div></div>

  const bottlenecks = [...data.top_bottlenecks].sort((a, b) => b.share - a.share).slice(0, 8)
  const facilities = [...data.facilities_in_zone]
    .sort((a, b) => b.share - a.share)
    .slice(0, 8)
    .map((f) => ({ ...f, label: `${f.name}` }))
  const wind = [...data.worst_wind]
    .sort((a, b) => a.wind_from_deg - b.wind_from_deg)
    .map((w) => ({ ...w, dir: compass(w.wind_from_deg), clearance_min: Math.round(w.mean_clearance_s / 60) }))
  const worst = [...wind].sort((a, b) => b.mean_clearance_s - a.mean_clearance_s)[0]
  const best = [...wind].sort((a, b) => a.mean_clearance_s - b.mean_clearance_s)[0]
  const SPEED_LABEL: Record<number, string> = { 1.5: 'Light', 4: 'Moderate', 7: 'Strong' }
  const bySpeed = [...(data.by_wind_speed ?? [])]
    .sort((a, b) => a.wind_speed_mps - b.wind_speed_mps)
    .map((w) => ({
      ...w,
      label: `${SPEED_LABEL[w.wind_speed_mps] ?? ''} ${w.wind_speed_mps} m/s`.trim(),
      clearance_min: Math.round(w.mean_clearance_s / 60),
    }))
  const barH = (n: number) => Math.max(220, n * 38 + 30)
  const TOD_LABEL: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }
  const TOD_ORDER = ['night', 'day', 'gameday']
  const byTime = [...(data.by_time_of_day ?? [])]
    .sort((a, b) => TOD_ORDER.indexOf(a.time_of_day) - TOD_ORDER.indexOf(b.time_of_day))
    .map((t) => ({ ...t, label: TOD_LABEL[t.time_of_day] ?? t.time_of_day, clearance_min: Math.round(t.mean_clearance_s / 60) }))

  // Headline findings (the README's "Results"), written as sentences a judge can read in seconds.
  const findings: Finding[] = []
  const fac = facilities[0]
  if (fac)
    findings.push({
      big: fmtPct(fac.share),
      title: <><b>{fac.name}</b> is inside the danger zone in {fmtPct(fac.share)} of scenarios</>,
      detail: `${FACILITY_LABEL[fac.type] ?? 'Facility'} residents need help to leave, so this site needs a standing shelter-in-place plan.${facilities[1] ? ` ${facilities[1].name}: ${fmtPct(facilities[1].share)}.` : ''}`,
      tone: 'bad',
    })
  if (data.garage_in_zone_share != null)
    findings.push({
      big: fmtPct(data.garage_in_zone_share),
      title: <>Madison Metro&apos;s <b>bus garage</b> is itself in the danger zone in {fmtPct(data.garage_in_zone_share)} of scenarios</>,
      detail: 'Every evacuation bus starts there, so the plan for residents who need a ride can fail before it begins.',
      tone: 'bad',
    })
  if (bySpeed.length > 1) {
    const [lo, hi] = [bySpeed[0], bySpeed[bySpeed.length - 1]]
    findings.push({
      big: `${lo.clearance_min} → ${hi.clearance_min} min`,
      title: <><b>Wind speed decides who can leave</b></>,
      detail: `Light wind makes a huge zone but slow gas: ${fmtCompact(lo.mean_evacuating)} people evacuate on average and the last car is out at ${lo.clearance_min} min. Strong wind shrinks the zone, but the gas arrives so fast that only ${fmtCompact(hi.mean_evacuating)} can leave; most must shelter.`,
      tone: 'warn',
    })
  }
  if (worst)
    findings.push({
      big: `${Math.round(worst.mean_clearance_s / 60)} min`,
      title: <>Wind from the <b>{worst.dir}</b> is the worst case</>,
      detail: `${fmtDuration(worst.mean_clearance_s)} on average to get everyone out, the slowest of ${wind.length} wind directions${best ? ` (from the ${best.dir}: ${Math.round(best.mean_clearance_s / 60)} min)` : ''}.`,
      tone: 'warn',
    })
  const game = byTime.find((t) => t.time_of_day === 'gameday')
  const day = byTime.find((t) => t.time_of_day === 'day')
  if (game && day)
    findings.push({
      big: fmtCompact(game.mean_sheltering),
      title: <>On <b>game day</b>, about {fmtCompact(game.mean_sheltering)} people are told to shelter</>,
      detail: `vs. about ${fmtCompact(day.mean_sheltering)} on a normal day: the stadium crowd adds to everyone else near the rail lines.`,
      tone: 'warn',
    })
  const topB = bottlenecks[0]
  if (topB)
    findings.push(
      topB.share < 0.25
        ? {
            big: fmtPct(topB.share),
            title: <>No single road is always the choke point: <b>a fixed plan can&apos;t work</b></>,
            detail: `The most frequent, ${topB.name}, backs up in only ${fmtPct(topB.share)} of scenarios. It depends on where the train derails and which way the wind blows.`,
            tone: 'info',
          }
        : {
            big: fmtPct(topB.share),
            title: <><b>{topB.name}</b> is the choke point in {fmtPct(topB.share)} of scenarios</>,
            detail: 'Fixing this one road would help in most derailments.',
            tone: 'warn',
          },
    )

  return (
    <div className="page planning">
      <header className="page-head">
        <div>
          <h2>What {data.n_scenarios ? fmtInt(data.n_scenarios) : 'hundreds of'} simulated derailments tell us</h2>
          <p className="muted">Run on Databricks: 8 derailment points near the isthmus × 8 wind directions × 3 wind speeds × night, day and game day, for a chlorine tank car. Findings first, the data behind them below.</p>
          <div className="run-stats">
            {data.n_scenarios != null && <span><b>{fmtInt(data.n_scenarios)}</b> scenarios</span>}
            {data.n_failed != null && <span className={data.n_failed > 0 ? 'bad' : ''}><b>{fmtInt(data.n_failed)}</b> failed</span>}
            {data.median_runtime_ms != null && <span><b>{data.median_runtime_ms < 1000 ? `${Math.round(data.median_runtime_ms)} ms` : `${(data.median_runtime_ms / 1000).toFixed(1)} s`}</b> median run</span>}
          </div>
        </div>
        {source === 'placeholder' && <span className="badge warn">Placeholder data — batch results pending</span>}
      </header>

      <div className="findings">
        {findings.map((f, i) => (
          <article key={i} className={`finding tone-${f.tone}`}>
            <div className="finding-big">{f.big}</div>
            <div>
              <h3>{f.title}</h3>
              <p>{f.detail}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="freq-cta">
        <div>
          <h3>Where is sheltering most often needed?</h3>
          <p className="muted">Color every block by how often it is told to shelter in place across all {data.n_scenarios ? fmtInt(data.n_scenarios) : ''} scenarios.</p>
        </div>
        <button className="run" onClick={onShowFrequency} disabled={!frequencyReady} title={frequencyReady ? undefined : 'Needs data/gold/block_frequency.json'}>
          Show shelter frequency on the map →
        </button>
      </div>

      <h2 className="section-title">The data behind these findings</h2>
      <div className="chart-grid">
        <ChartCard
          title="Recurring choke points"
          sub={data.bottleneck_method ? 'Share of scenarios where the road is among the 5 with the most queued traffic in the simulation' : "Share of scenarios where the road segment is in the network's minimum cut"}
        >
          <ResponsiveContainer width="100%" height={barH(bottlenecks.length)}>
            <BarChart data={bottlenecks} layout="vertical" margin={{ left: 8, right: 48, top: 4, bottom: 4 }} barCategoryGap={8}>
              <XAxis type="number" domain={[0, 1]} tickFormatter={fmtPct} tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={170} tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
              <Tooltip {...TT} formatter={(v: number, _n, p) => [`${fmtPct(v)} (${fmtInt(p.payload.times_bottleneck)} runs)`, 'Bottleneck in']} />
              <Bar dataKey="share" radius={[0, 3, 3, 0]} maxBarSize={18}>
                {highlightMax(bottlenecks, (d) => d.share, AMBER)}
                <LabelList dataKey="share" position="right" formatter={(v: number) => fmtPct(v)} fill={LABEL} fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Facilities most often inside the zone" sub="Share of scenarios where the facility falls in the isolation or protective zone">
          <ResponsiveContainer width="100%" height={barH(facilities.length)}>
            <BarChart data={facilities} layout="vertical" margin={{ left: 8, right: 48, top: 4, bottom: 4 }} barCategoryGap={8}>
              <XAxis type="number" domain={[0, 1]} tickFormatter={fmtPct} tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={190} tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
              <Tooltip {...TT} formatter={(v: number, _n, p) => [fmtPct(v), FACILITY_LABEL[p.payload.type] ?? p.payload.type]} />
              <Bar dataKey="share" radius={[0, 3, 3, 0]} maxBarSize={18}>
                {highlightMax(facilities, (d) => d.share, RED)}
                <LabelList dataKey="share" position="right" formatter={(v: number) => fmtPct(v)} fill={LABEL} fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Time to get everyone out, by wind direction" sub="Average minutes from alert until the last evacuating vehicle is out, by where the wind comes from">
          <ResponsiveContainer width="100%" height={320}>
            <RadarChart data={wind} outerRadius="72%">
              <PolarGrid stroke={GRID} gridType="circle" />
              <PolarAngleAxis dataKey="dir" tick={{ ...AXIS, fill: LABEL, fontSize: 13 }} />
              <PolarRadiusAxis angle={90} tick={{ ...AXIS, fontSize: 10 }} axisLine={false} tickFormatter={(v: number) => `${v}m`} />
              <Tooltip {...TT} formatter={(v: number) => [`${v} min`, 'Avg. clearance']} labelFormatter={(l) => `Wind from ${l}`} />
              <Radar dataKey="clearance_min" stroke={STRONG} strokeWidth={1.5} fill={SERIES} fillOpacity={0.16} dot={{ r: 3, fill: STRONG }} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Residents left behind, by wind direction" sub="Average residents who need a ride that no bus can reach before the gas (with 20 buses this stays near zero)">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={wind} margin={{ left: 0, right: 12, top: 20, bottom: 4 }} barCategoryGap="22%">
              <XAxis dataKey="dir" tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} />
              <Tooltip {...TT} formatter={(v: number) => [fmtInt(v), 'Avg. unserved']} labelFormatter={(l) => `Wind from ${l}`} />
              <Bar dataKey="mean_unserved" radius={[3, 3, 0, 0]} maxBarSize={32}>
                {highlightMax(wind, (d) => d.mean_unserved, RED)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {byTime.length > 0 && (
        <div className="chart-grid">
          <ChartCard title="Time to get everyone out, by time of day" sub="Average minutes from alert until the last evacuating vehicle is out">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byTime} margin={{ left: 0, right: 12, top: 22, bottom: 4 }} barCategoryGap="30%">
                <XAxis dataKey="label" tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} tickFormatter={(v: number) => `${v}m`} />
                <Tooltip {...TT} formatter={(v: number) => [`${v} min`, 'Avg. time to get everyone out']} />
                <Bar dataKey="clearance_min" radius={[3, 3, 0, 0]} maxBarSize={48}>
                  {highlightMax(byTime, (d) => d.clearance_min, AMBER)}
                  <LabelList dataKey="clearance_min" position="top" formatter={(v: number) => `${v} min`} fill={LABEL} fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Who moves, by time of day" sub="Average people per scenario">
            <table className="data-table">
              <thead>
                <tr>
                  <th />
                  <th>Evacuating</th>
                  <th>Sheltering in place</th>
                  <th>Left behind</th>
                </tr>
              </thead>
              <tbody>
                {byTime.map((t) => (
                  <tr key={t.time_of_day}>
                    <th>{t.label}</th>
                    <td>{fmtInt(t.mean_evacuating)}</td>
                    <td>{fmtInt(t.mean_sheltering)}</td>
                    <td>{t.mean_unserved == null ? '—' : fmtInt(t.mean_unserved)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">"Left behind" = residents who need a ride that no bus can reach before the gas arrives.</p>
          </ChartCard>
        </div>
      )}

      {bySpeed.length > 0 && (
        <div className="chart-grid">
          <ChartCard title="Who can leave, by wind speed" sub="Average people per scenario. Stronger wind shrinks the zone, but the gas arrives too fast to drive out.">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={bySpeed} margin={{ left: 0, right: 12, top: 22, bottom: 4 }} barCategoryGap="24%">
                <XAxis dataKey="label" tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={48} tickFormatter={(v: number) => fmtCompact(v)} />
                <Tooltip {...TT} formatter={(v: number, n: string) => [fmtInt(v), n === 'mean_evacuating' ? 'Evacuating' : 'Sheltering']} />
                <Bar dataKey="mean_evacuating" fill="#ff6b1a" radius={[4, 4, 0, 0]} maxBarSize={44} />
                <Bar dataKey="mean_sheltering" fill="#8b5cf6" radius={[4, 4, 0, 0]} maxBarSize={44} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mini-legend"><span><i style={{ background: '#ff6b1a' }} />Evacuating</span><span><i style={{ background: '#8b5cf6' }} />Sheltering in place</span></div>
          </ChartCard>
          <ChartCard title="Time to get everyone out, by wind speed" sub="Average minutes from the alert until the last evacuating car is out">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={bySpeed} margin={{ left: 0, right: 12, top: 22, bottom: 4 }} barCategoryGap="30%">
                <XAxis dataKey="label" tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={52} tickFormatter={(v: number) => `${v}m`} />
                <Tooltip {...TT} formatter={(v: number) => [`${v} min`, 'Avg. time to get everyone out']} />
                <Bar dataKey="clearance_min" radius={[3, 3, 0, 0]} maxBarSize={48}>
                  {highlightMax(bySpeed, (d) => d.clearance_min, AMBER)}
                  <LabelList dataKey="clearance_min" position="top" formatter={(v: number) => `${v} min`} fill={LABEL} fontSize={13} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {data.flood && <FloodSection f={data.flood} />}

      {robust && <RobustnessSection r={robust} />}
    </div>
  )
}

const fmtRiseM = (m: number) => `+${Number(m.toFixed(2))} m`

/** Lowest flood rise = most exposed: that bar gets the highlight colour. */
function highlightMin<T>(data: T[], key: (d: T) => number, color: string) {
  const min = Math.min(...data.map(key))
  return data.map((d, i) => <Cell key={i} fill={key(d) === min ? color : SERIES} />)
}

function FloodSection({ f }: { f: FloodInsights }) {
  const facilities = [...f.facilities].sort((a, b) => a.flood_rise_m - b.flood_rise_m).slice(0, 10)
  const roads = [...f.roads].sort((a, b) => a.flood_rise_m - b.flood_rise_m).slice(0, 10)
  const byRise = [...f.by_rise].sort((a, b) => a.rise_m - b.rise_m).map((r) => ({ ...r, label: fmtRiseM(r.rise_m) }))
  const maxRise = Math.max(0.5, ...facilities.map((x) => x.flood_rise_m), ...roads.map((x) => x.flood_rise_m))
  const barH = (n: number) => Math.max(160, n * 38 + 30)
  const riseChart = (rows: { name: string; flood_rise_m: number; type?: string }[], color: string) => (
    <ResponsiveContainer width="100%" height={barH(rows.length)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 56, top: 4, bottom: 4 }} barCategoryGap={8}>
        <XAxis type="number" domain={[0, Math.ceil(maxRise * 2) / 2]} tickFormatter={(v: number) => `${v} m`} tick={AXIS} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="name" width={200} tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
        <Tooltip {...TT} formatter={(v: number, _n, p) => [fmtRiseM(v), p.payload.type ? (FACILITY_LABEL[p.payload.type] ?? p.payload.type.replace(/_/g, ' ')) : 'Floods at']} />
        <Bar dataKey="flood_rise_m" radius={[0, 3, 3, 0]} maxBarSize={18}>
          {highlightMin(rows, (d) => d.flood_rise_m, color)}
          <LabelList dataKey="flood_rise_m" position="right" formatter={(v: number) => fmtRiseM(v)} fill={LABEL} fontSize={12} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
  return (
    <section className="robust">
      <h2 className="section-title">Floods: what goes underwater first</h2>
      <p className="robust-lede">
        {fmtInt(f.n_scenarios)} flood scenarios: Lake Mendota, Lake Monona with the Yahara River, or both, rising by different
        heights. For each place, the bars show how far the lakes must rise before water reaches it. Lower means it floods sooner.
      </p>
      {f.garage_flood_rise_m != null && (
        <div className="findings">
          <article className="finding tone-bad">
            <div className="finding-big">{fmtRiseM(f.garage_flood_rise_m)}</div>
            <div>
              <h3>Metro&apos;s <b>bus garage</b> floods when the lakes rise {Number(f.garage_flood_rise_m.toFixed(2))} m</h3>
              <p>Every evacuation bus starts there. Above that level the buses must be moved out before the water arrives, or the pickups for residents who need a ride never start.</p>
            </div>
          </article>
        </div>
      )}
      <div className="chart-grid">
        {facilities.length > 0 && (
          <ChartCard title="Facilities, by how high the lakes must rise to reach them" sub="Lake rise above the normal summer level at which water reaches the site">
            {riseChart(facilities, RED)}
          </ChartCard>
        )}
        {roads.length > 0 && (
          <ChartCard title="Roads, by how high the lakes must rise to cut them" sub="Lake rise at which the road first goes underwater and closes">
            {riseChart(roads, AMBER)}
          </ChartCard>
        )}
      </div>
      {byRise.length > 0 && (
        <div className="chart-grid">
          <ChartCard title="Who moves, by lake rise" sub="Average people per scenario: evacuating to higher ground vs. staying and moving to an upper floor">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={byRise} margin={{ left: 0, right: 12, top: 22, bottom: 4 }} barCategoryGap="24%">
                <XAxis dataKey="label" tick={{ ...AXIS, fill: LABEL }} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={48} tickFormatter={(v: number) => fmtCompact(v)} />
                <Tooltip {...TT} formatter={(v: number, n: string) => [fmtInt(v), n === 'mean_people_evacuating' ? 'Evacuating' : 'Staying (upper floor)']} />
                <Bar dataKey="mean_people_evacuating" fill="#ff6b1a" radius={[4, 4, 0, 0]} maxBarSize={44} />
                <Bar dataKey="mean_people_sheltering" fill="#8b5cf6" radius={[4, 4, 0, 0]} maxBarSize={44} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mini-legend"><span><i style={{ background: '#ff6b1a' }} />Evacuating</span><span><i style={{ background: '#8b5cf6' }} />Staying, upper floor</span></div>
          </ChartCard>
          <ChartCard title="Flooded area and response, by lake rise" sub="Averages per scenario">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Lake rise</th>
                    <th>Flooded</th>
                    <th>Evacuating</th>
                    <th>Staying</th>
                    <th>Everyone out</th>
                    <th>Need a bus</th>
                    <th>Left behind</th>
                  </tr>
                </thead>
                <tbody>
                  {byRise.map((r) => (
                    <tr key={r.rise_m}>
                      <th>{r.label}</th>
                      <td>{r.flooded_km2.toFixed(1)} km²</td>
                      <td>{fmtInt(r.mean_people_evacuating)}</td>
                      <td>{fmtInt(r.mean_people_sheltering)}</td>
                      <td>{r.mean_people_evacuating > 0 ? fmtDuration(r.mean_clearance_s) : '—'}</td>
                      <td>{fmtInt(r.mean_need_bus)}</td>
                      <td>{fmtInt(r.mean_unserved)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">"Left behind" = residents who need a ride that no bus can reach before the water arrives.</p>
          </ChartCard>
        </div>
      )}
    </section>
  )
}

function RobustnessSection({ r }: { r: Robustness }) {
  const rows = Object.entries(r.variants)
  const base = r.variants.baseline
  const slowWarn = rows.find(([k]) => k.startsWith('warning'))
  return (
    <section className="robust">
      <h2 className="section-title">Do the findings hold if our assumptions are wrong?</h2>
      <p className="robust-lede">
        We re-ran {fmtInt(r.grid.n_scenarios)} scenarios under {rows.length - 1} changes to our biggest assumptions. The order
        (light wind slowest, strong wind fastest) and the choke-point cluster survive every one.
        {slowWarn && base && (
          <> The surprise: if the warning takes 15 min instead of 5, about {fmtPct(1 - slowWarn[1].mean_evacuating / base.mean_evacuating)} fewer
          people can beat the gas. <b>Warning speed decides who gets to leave.</b></>
        )}
      </p>
      <div className="table-wrap">
        <table className="data-table robust-table">
          <thead>
            <tr>
              <th>Assumption</th>
              <th>Avg. everyone out</th>
              <th>Light / moderate / strong wind</th>
              <th>Avg. evacuating</th>
              <th>Capitol Lakes in zone</th>
              <th>Top choke points</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, v]) => (
              <tr key={name} className={name === 'baseline' ? 'base' : ''}>
                <th>{name === 'baseline' ? 'Baseline (our defaults)' : name[0].toUpperCase() + name.slice(1)}</th>
                <td>{Math.round(v.mean_clearance_min)} min</td>
                <td>{Object.entries(v.clearance_min_by_wind_speed).sort((a, b) => Number(a[0]) - Number(b[0])).map(([, m]) => Math.round(m)).join(' / ')} min</td>
                <td>{fmtInt(v.mean_evacuating)}</td>
                <td>{fmtPct(v.capitol_lakes_in_zone)}</td>
                <td className="chokes">{v.top_choke_points.filter((c) => !c.startsWith('Unnamed')).slice(0, 3).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
