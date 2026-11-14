"""Run a few scenarios and print summaries + timings.

    python -m engine.run_demo                 # data/silver → data/fixtures → synthetic grid
    python -m engine.run_demo path/to/silver
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import shapely

from contracts.engine_api import ScenarioParams
from engine.network import load_network
from engine.scenario import run_with_diagnostics
from engine.synthetic import write_synthetic

REPO = Path(__file__).resolve().parents[1]


def pick_data_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    for cand in (REPO / "data" / "silver", REPO / "data" / "fixtures"):
        if (cand / "road_nodes.parquet").exists():
            return cand
    tmp = Path(tempfile.mkdtemp(prefix="isthmus_synth_"))
    print(f"(no silver/fixtures yet — using synthetic grid in {tmp})")
    return write_synthetic(tmp)


def fmt(s: float) -> str:
    return f"{s / 60:5.1f} min"


def main(argv: list[str]) -> None:
    data_dir = pick_data_dir(argv[1] if len(argv) > 1 else None)
    t0 = time.perf_counter()
    net = load_network(data_dir)
    print(f"network: {net.G.number_of_nodes()} nodes, {net.G.number_of_edges()} edges, "
          f"{len(net.blocks)} blocks  (loaded in {(time.perf_counter() - t0) * 1000:.0f} ms)")

    if net.rails:
        p = shapely.line_interpolate_point(net.rails[0], 0.4, normalized=True)
        lon, lat = p.x, p.y
    else:
        lons = [d["lon"] for _, d in net.G.nodes(data=True)]
        lats = [d["lat"] for _, d in net.G.nodes(data=True)]
        lon, lat = sum(lons) / len(lons), sum(lats) / len(lats)

    base = dict(release_lon=lon, release_lat=lat, chemical="chlorine", spill_size="large",
                wind_from_deg=225.0, wind_speed_mps=3.0)
    scenarios = {
        "day": ScenarioParams(**base, time_of_day="day"),
        "day + contraflow": ScenarioParams(**base, time_of_day="day", contraflow=True),
        "night": ScenarioParams(**base, time_of_day="night"),
        "game day": ScenarioParams(**base, time_of_day="gameday"),
        "fast wind (6 m/s)": ScenarioParams(**{**base, "wind_speed_mps": 6.0}, time_of_day="day"),
    }
    for name, params in scenarios.items():
        r, d = run_with_diagnostics(params, net)
        s = r.summary
        decisions = {}
        for b in r.blocks:
            decisions[b.decision] = decisions.get(b.decision, 0) + 1
        print(f"\n== {name}")
        print(f"  clearance (flow plan)  {fmt(s.clearance_time_s)}   sim check {fmt(d.sim_clearance_s)}"
              f"   capacity-limited {fmt(d.capacity_time_s)}")
        print(f"  vehicles {d.vehicles:,}   evacuating {s.people_evacuating:,.0f}   "
              f"sheltering {s.people_sheltering:,.0f}   blocks {decisions}")
        print(f"  need bus {s.need_bus_total:,.0f}   unserved {s.need_bus_unserved:,.0f}   "
              f"buses used {len(r.buses)}   bottlenecks {s.bottleneck_edge_ids[:6]}")
        print(f"  runtime {s.runtime_ms:,.0f} ms   {d.timings_ms}"
              + ("   [road rules relaxed]" if d.relaxed_road_rules else ""))


if __name__ == "__main__":
    main(sys.argv)
