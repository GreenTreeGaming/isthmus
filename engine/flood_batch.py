"""Flood findings for the Planning tab and Databricks.

    python -m engine.flood_batch data/silver --out data/gold     # adds a "flood" key to data/gold/insights.json

Two kinds of result:
1. Thresholds (no simulation needed): how far the lakes must rise before each hospital, nursing home, the Metro
   garage, each candidate shelter and each major road goes underwater — straight from the flood grid.
2. A scenario grid: lake source × rise × time to peak × time of day, each run through the full engine.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.engine_api import ScenarioParams
from engine import assumptions as A
from engine.flood import FloodHazard
from engine.network import Network, load_network
from engine.scenario import make_hazard, run_with_diagnostics

SOURCES = ("mendota", "monona", "both")
RISES_M = (0.5, 1.0, 1.5, 2.0, 3.0)
PEAKS_H = (3.0, 12.0)
TIMES = ("night", "day", "gameday")
MAJOR_ROADS = {"primary", "secondary"}            # highways are treated as raised (A.FLOOD_ELEVATED_CLASSES)
MAX_REPORTED_RISE_M = 3.0

FLOOD_RESULT_SCHEMA = (
    "scenario_id long, flood_source string, flood_rise_m double, flood_peak_h double, time_of_day string, "
    "flooded_km2 double, clearance_time_s double, sim_clearance_s double, people_evacuating double, "
    "people_sheltering double, need_bus_total double, need_bus_unserved double, n_evacuate long, n_shelter long, "
    "garage_in_zone boolean, facilities_in_zone string, runtime_ms double, error string"
)


def flood_grid(sources=SOURCES, rises=RISES_M, peaks=PEAKS_H, times=TIMES) -> pd.DataFrame:
    rows = [dict(scenario_id=i, flood_source=s, flood_rise_m=float(r), flood_peak_h=float(p), time_of_day=t)
            for i, (s, r, p, t) in enumerate(itertools.product(sources, rises, peaks, times))]
    return pd.DataFrame(rows)


def flooded_km2(net: Network, source: str, rise_m: float) -> float:
    g = net.flood
    land = g.lake_code == 0
    return float((land & (g.rise[source] <= rise_m)).sum() * g.cell ** 2 / 1e6)


def run_flood_row(row, net: Network, bus_time_limit_s: float = 0.3) -> dict:
    A.BUS_SOLVER_TIME_LIMIT_S = bus_time_limit_s
    lon, lat = net.G.nodes[next(iter(net.G.nodes))]["lon"], net.G.nodes[next(iter(net.G.nodes))]["lat"]
    p = ScenarioParams(release_lon=float(lon), release_lat=float(lat), hazard="flood",
                       flood_source=row["flood_source"], flood_rise_m=float(row["flood_rise_m"]),
                       flood_peak_h=float(row["flood_peak_h"]), time_of_day=row["time_of_day"])
    out = dict(scenario_id=int(row["scenario_id"]), flood_source=p.flood_source, flood_rise_m=p.flood_rise_m,
               flood_peak_h=p.flood_peak_h, time_of_day=p.time_of_day,
               flooded_km2=round(flooded_km2(net, p.flood_source, p.flood_rise_m), 3), error=None)
    try:
        r, d = run_with_diagnostics(p, net)
    except Exception as exc:
        out.update(error=f"{type(exc).__name__}: {exc}")
        return out
    s = r.summary
    hz = make_hazard(net, p)
    fac = []
    if not net.facilities.empty:
        inside = hz.in_zone(net.facilities["x"].to_numpy(), net.facilities["y"].to_numpy())
        fac = net.facilities.loc[inside, "facility_id"].astype(str).tolist()
    gar = net.depots[net.depots["kind"] == "bus_garage"] if not net.depots.empty else net.depots
    out.update(clearance_time_s=s.clearance_time_s, sim_clearance_s=s.sim_clearance_s,
               people_evacuating=s.people_evacuating, people_sheltering=s.people_sheltering,
               need_bus_total=s.need_bus_total, need_bus_unserved=s.need_bus_unserved,
               n_evacuate=sum(b.decision == "evacuate" for b in r.blocks),
               n_shelter=sum(b.decision == "shelter" for b in r.blocks),
               garage_in_zone=bool(hz.in_zone(gar["x"].to_numpy(), gar["y"].to_numpy()).any()) if len(gar) else None,
               facilities_in_zone=json.dumps(fac), runtime_ms=s.runtime_ms)
    return out


def thresholds(net: Network, source: str = "both") -> dict:
    """How far the lake(s) must rise before each place / major road floods (≤ MAX_REPORTED_RISE_M)."""
    hz = FloodHazard(grid=net.flood, source=source, rise_m=1.0, peak_s=3600.0, zone=None, region=None)
    places = []
    for f in net.facilities.itertuples(index=False):
        places.append((str(f.name), str(f.type), float(hz.need(f.x, f.y))))
    for dpt in net.depots.itertuples(index=False):
        places.append((str(dpt.name), str(dpt.kind), float(hz.need(dpt.x, dpt.y))))
    facilities = sorted(({"name": n, "type": t, "flood_rise_m": round(r, 2)} for n, t, r in places
                         if r <= MAX_REPORTED_RISE_M), key=lambda x: x["flood_rise_m"])
    garage = [r for n, t, r in places if t == "bus_garage"]

    G = net.G
    nodes = list(G.nodes)
    need = dict(zip(nodes, hz.need(np.array([G.nodes[n]["x"] for n in nodes]),
                                   np.array([G.nodes[n]["y"] for n in nodes]))))
    first_cut: dict[str, float] = {}
    for u, v, d in G.edges(data=True):
        name = d.get("name")
        if d.get("road_class") not in MAJOR_ROADS or not isinstance(name, str) or not name:
            continue
        r = min(need[u], need[v])            # a road is cut where its lowest end goes under
        name = name.replace(" 1st ", " First ")   # OSM spells it both ways
        first_cut[name] = min(first_cut.get(name, np.inf), r)
    roads = sorted(({"name": n, "flood_rise_m": round(float(r), 2)} for n, r in first_cut.items()
                    if r <= MAX_REPORTED_RISE_M), key=lambda x: x["flood_rise_m"])
    return {"facilities": facilities, "roads": roads[:15],
            "garage_flood_rise_m": round(garage[0], 2) if garage and garage[0] <= MAX_REPORTED_RISE_M else None}


def flood_insights(results: pd.DataFrame, net: Network) -> dict:
    ok = results[results["error"].isna()] if "error" in results else results
    both = ok[ok["flood_source"] == "both"]
    by_rise = (both.groupby("flood_rise_m")
               .agg(flooded_km2=("flooded_km2", "first"), mean_people_evacuating=("people_evacuating", "mean"),
                    mean_people_sheltering=("people_sheltering", "mean"), mean_clearance_s=("sim_clearance_s", "mean"),
                    mean_need_bus=("need_bus_total", "mean"), mean_unserved=("need_bus_unserved", "mean"))
               .reset_index().rename(columns={"flood_rise_m": "rise_m"}))
    by_source = (ok.groupby(["flood_source", "flood_rise_m"])
                 .agg(flooded_km2=("flooded_km2", "first"), mean_people_evacuating=("people_evacuating", "mean"))
                 .reset_index().rename(columns={"flood_rise_m": "rise_m"}))
    by_peak = (both.groupby("flood_peak_h")
               .agg(mean_people_evacuating=("people_evacuating", "mean"),
                    mean_people_sheltering=("people_sheltering", "mean"), mean_unserved=("need_bus_unserved", "mean"))
               .reset_index().rename(columns={"flood_peak_h": "peak_h"}))
    r1 = lambda df: json.loads(df.round(2).to_json(orient="records"))  # noqa: E731
    return {"n_scenarios": int(len(results)), "n_failed": int(results["error"].notna().sum()),
            "source_for_thresholds": "both", "by_rise": r1(by_rise), "by_source": r1(by_source),
            "by_peak": r1(by_peak), **thresholds(net)}


_NET: dict[str, Network] = {}


def _init(data_dir):
    _NET[data_dir] = load_network(data_dir)


def _run(args):
    row, data_dir = args
    return run_flood_row(row, _NET[data_dir])


def run_local(grid: pd.DataFrame, data_dir: str, workers: int | None = None) -> pd.DataFrame:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    rows = [r for _, r in grid.iterrows()]
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(data_dir,)) as ex:
        return pd.DataFrame(list(ex.map(_run, [(r, data_dir) for r in rows], chunksize=2)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the flood scenario grid and add 'flood' to insights.json.")
    ap.add_argument("data_dir")
    ap.add_argument("--out", default="data/gold")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    net = load_network(a.data_dir)
    grid = flood_grid()
    print(f"running {len(grid)} flood scenarios …")
    t0 = time.time()
    res = run_local(grid, a.data_dir, a.workers)
    print(f"done in {time.time() - t0:.0f}s, {res['error'].notna().sum()} failed")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "insights.json"
    insights = json.loads(path.read_text()) if path.exists() else {}
    insights["flood"] = flood_insights(res, net)
    path.write_text(json.dumps(insights, indent=1))
    res.to_json(out / "flood_results.json", orient="records")
    print("wrote", path)
    print(json.dumps({k: insights["flood"][k] for k in ("garage_flood_rise_m", "facilities", "roads")}, indent=1)[:2500])


if __name__ == "__main__":
    main()
