import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, LabelList, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getInsights } from '../api'
import type { Insights } from '../types'
import { compass, fmtDuration, fmtInt, fmtPct } from '../lib/format'

const SERIES = '#3987e5'
const GRID = 'rgba(148,163,184,0.14)'
const AXIS = { fill: '#94a3b8', fontSize: 12 }
const TT = {
  contentStyle: { background: '#111821', border: '1px solid #263241', borderRadius: 8, fontSize: 12.5 },
  labelStyle: { color: '#e6edf5', fontWeight: 600 },
  itemStyle: { color: '#c3cfdc' },
  cursor: { fill: 'rgba(148,163,184,0.08)' },
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

  useEffect(() => {
    getInsights()
      .then((r) => {
        setData(r.data)
        setSource(r.source)
      })
      .catch((e: Error) => setError(e.message))
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
  const barH = (n: number) => Math.max(220, n * 38 + 30)
  const TOD_LABEL: Record<string, string> = { night: 'Night', day: 'Day', gameday: 'Game day' }
  const TOD_ORDER = ['night', 'day', 'gameday']
  const byTime = [...(data.by_time_of_day ?? [])]
    .sort((a, b) => TOD_ORDER.indexOf(a.time_of_day) - TOD_ORDER.indexOf(b.time_of_day))
    .map((t) => ({ ...t, label: TOD_LABEL[t.time_of_day] ?? t.time_of_day, clearance_min: Math.round(t.mean_clearance_s / 60) }))

  // Headline findings, written as sentences a judge can read in seconds.
  const findings: Finding[] = []
  const fac = facilities[0]
  if (fac)
    findings.push({
      big: fmtPct(fac.share),
      title: <><b>{fac.name}</b> is inside the danger zone in {fmtPct(fac.share)} of scenarios</>,
      detail: `${FACILITY_LABEL[fac.type] ?? 'Facility'} residents need help to leave, so this site needs a standing shelter-in-place plan.`,
      tone: 'bad',
    })
  if (byTime.length > 1) {
    const slow = [...byTime].sort((a, b) => b.mean_clearance_s - a.mean_clearance_s)
    const [worstT, bestT] = [slow[0], slow[slow.length - 1]]
    findings.push({
      big: `${worstT.clearance_min} min`,
      title: <><b>{worstT.label}</b> takes longest to get everyone out</>,
      detail: `${worstT.clearance_min} min on average, vs. ${bestT.clearance_min} min for ${bestT.label.toLowerCase()}.`,
      tone: 'warn',
    })
  }
  const topB = bottlenecks[0]
  if (topB)
    findings.push(
      topB.share < 0.25
        ? {
            big: fmtPct(topB.share),
            title: <>No single road is always the bottleneck — <b>plans must adapt</b></>,
            detail: `The most frequent, ${topB.name}, is the choke point in only ${fmtPct(topB.share)} of scenarios. It depends on where the train derails and where the wind blows.`,
            tone: 'info',
          }
        : {
            big: fmtPct(topB.share),
            title: <><b>{topB.name}</b> is the choke point in {fmtPct(topB.share)} of scenarios</>,
            detail: 'Fixing this one road would help in most derailments.',
            tone: 'warn',
          },
    )
  if (worst)
    findings.push({
      big: `${Math.round(worst.mean_clearance_s / 60)} min`,
      title: <>Wind from the <b>{worst.dir}</b> is the worst case</>,
      detail: `${fmtDuration(worst.mean_clearance_s)} on average to get everyone out — the slowest of ${wind.length} wind directions.`,
      tone: 'warn',
    })

  return (
    <div className="page planning">
      <header className="page-head">
        <div>
          <h2>What {data.n_scenarios ? fmtInt(data.n_scenarios) : 'hundreds of'} simulated derailments tell us</h2>
          <p className="muted">Every rail location, wind direction, time of day and chemical, run as one batch. Findings first, charts below.</p>
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
        <ChartCard title="Top bottleneck roads" sub="Share of scenarios where the road segment is in the network's minimum cut">
          <ResponsiveContainer width="100%" height={barH(bottlenecks.length)}>
            <BarChart data={bottlenecks} layout="vertical" margin={{ left: 8, right: 48, top: 4, bottom: 4 }} barCategoryGap={8}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" domain={[0, 1]} tickFormatter={fmtPct} tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={170} tick={{ ...AXIS, fill: '#d6dee8' }} axisLine={false} tickLine={false} />
              <Tooltip {...TT} formatter={(v: number, _n, p) => [`${fmtPct(v)} (${fmtInt(p.payload.times_bottleneck)} runs)`, 'Bottleneck in']} />
              <Bar dataKey="share" fill={SERIES} radius={[0, 4, 4, 0]} maxBarSize={22}>
                <LabelList dataKey="share" position="right" formatter={(v: number) => fmtPct(v)} fill="#c3cfdc" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Facilities most often inside the zone" sub="Share of scenarios where the facility falls in the isolation or protective zone">
          <ResponsiveContainer width="100%" height={barH(facilities.length)}>
            <BarChart data={facilities} layout="vertical" margin={{ left: 8, right: 48, top: 4, bottom: 4 }} barCategoryGap={8}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" domain={[0, 1]} tickFormatter={fmtPct} tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={190} tick={{ ...AXIS, fill: '#d6dee8' }} axisLine={false} tickLine={false} />
              <Tooltip {...TT} formatter={(v: number, _n, p) => [fmtPct(v), FACILITY_LABEL[p.payload.type] ?? p.payload.type]} />
              <Bar dataKey="share" fill={SERIES} radius={[0, 4, 4, 0]} maxBarSize={22}>
                <LabelList dataKey="share" position="right" formatter={(v: number) => fmtPct(v)} fill="#c3cfdc" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Time to get everyone out, by wind direction" sub="Average minutes from alert until the last evacuating vehicle is out, by where the wind comes from">
          <ResponsiveContainer width="100%" height={320}>
            <RadarChart data={wind} outerRadius="72%">
              <PolarGrid stroke={GRID} />
              <PolarAngleAxis dataKey="dir" tick={{ ...AXIS, fill: '#d6dee8', fontSize: 13 }} />
              <PolarRadiusAxis angle={90} tick={{ ...AXIS, fontSize: 10 }} axisLine={false} tickFormatter={(v: number) => `${v}m`} />
              <Tooltip {...TT} formatter={(v: number) => [`${v} min`, 'Avg. clearance']} labelFormatter={(l) => `Wind from ${l}`} />
              <Radar dataKey="clearance_min" stroke={SERIES} strokeWidth={2} fill={SERIES} fillOpacity={0.28} dot={{ r: 3, fill: SERIES }} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Residents left waiting for a bus, by wind direction" sub="Average people needing a bus who are not picked up before the plume arrives">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={wind} margin={{ left: 0, right: 12, top: 20, bottom: 4 }} barCategoryGap="22%">
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="dir" tick={{ ...AXIS, fill: '#d6dee8' }} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} />
              <Tooltip {...TT} formatter={(v: number) => [fmtInt(v), 'Avg. unserved']} labelFormatter={(l) => `Wind from ${l}`} />
              <Bar dataKey="mean_unserved" fill={SERIES} radius={[4, 4, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {byTime.length > 0 && (
        <div className="chart-grid">
          <ChartCard title="Time to get everyone out, by time of day" sub="Average minutes from alert until the last evacuating vehicle is out">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byTime} margin={{ left: 0, right: 12, top: 22, bottom: 4 }} barCategoryGap="30%">
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis dataKey="label" tick={{ ...AXIS, fill: '#d6dee8' }} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} tickFormatter={(v: number) => `${v}m`} />
                <Tooltip {...TT} formatter={(v: number) => [`${v} min`, 'Avg. time to get everyone out']} />
                <Bar dataKey="clearance_min" fill={SERIES} radius={[4, 4, 0, 0]} maxBarSize={56}>
                  <LabelList dataKey="clearance_min" position="top" formatter={(v: number) => `${v} min`} fill="#c3cfdc" fontSize={12} />
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
                  <th>Waiting for a bus</th>
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
            <p className="muted small">"Waiting for a bus" = residents who need a bus and are not picked up before the plume arrives.</p>
          </ChartCard>
        </div>
      )}
    </div>
  )
}
