"""Batch scenarios: build a grid, run it (locally or on Databricks), aggregate into gold insights.

Local:
    python -m engine.batch cache/madison_test --n-points 8 --out data/gold
Databricks (notebook 03_batch_scenarios):
    from engine.batch import scenario_grid, run_partition, RESULT_SCHEMA
    grid = scenario_grid(load_network(SILVER))                       # pandas
    sdf = spark.createDataFrame(grid).repartition(64, "scenario_id")
    res = sdf.groupBy("scenario_id").applyInPandas(lambda pdf: run_partition(pdf, SILVER), RESULT_SCHEMA)
    res.write.mode("overwrite").saveAsTable("isthmus.scenario_results")
    gold = gold_tables(res.toPandas(), load_network(SILVER)); export_gold_json(gold, "/Volumes/.../gold")

The output of gold_tables()["insights"] matches the frontend's Insights type (top_bottlenecks,
facilities_in_zone, worst_wind) so data/gold/insights.json drops straight into the Planning tab.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from contracts.engine_api import ScenarioParams
from engine import assumptions as A
from engine.network import Network, load_network, to_lonlat, to_metric
from engine.scenario import run_with_diagnostics

PARAM_COLS = ["release_lon", "release_lat", "chemical", "spill_size", "wind_from_deg", "wind_speed_mps",
              "time_of_day", "compliance", "bus_count", "bus_capacity", "contraflow", "closed_edge_ids", "seed"]

# Spark DDL for applyInPandas output. List-like results are JSON strings; gold_tables() parses them.
RESULT_SCHEMA = (
    "scenario_id long, release_lon double, release_lat double, chemical string, spill_size string, "
    "wind_from_deg double, wind_speed_mps double, time_of_day string, compliance double, bus_count long, "
    "contraflow boolean, n_closed long, "
    "clearance_time_s double, sim_clearance_s double, people_evacuating double, people_sheltering double, "
    "need_bus_total double, need_bus_unserved double, vehicles long, n_evacuate long, n_shelter long, "
    "runtime_ms double, error string, "
    "bottleneck_edge_ids string, shelter_block_ids string, evacuate_block_ids string, facilities_in_zone string"
)


# --------------------------------------------------------------------------- grid

def release_points(net: Network, n: int, max_from_center_m: float | None = None) -> list[tuple[float, float]]:
    """n points spread evenly (by distance) along the rail lines inside the study area."""
    if not net.rails:
        raise ValueError("no rail lines in the network — can't place derailments")
    xs = [d["x"] for _, d in net.G.nodes(data=True)]
    ys = [d["y"] for _, d in net.G.nodes(data=True)]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    limit = max_from_center_m or 0.45 * min(max(xs) - min(xs), max(ys) - min(ys))

    def metric(line):
        return shapely.transform(line, lambda c: np.column_stack(to_metric(c[:, 0], c[:, 1])))

    rails = shapely.unary_union([metric(r) for r in net.rails])
    core = shapely.Point(cx, cy).buffer(limit)
    inside = shapely.intersection(rails, core)
    if inside.is_empty or inside.length == 0:
        inside = rails
    merged = shapely.line_merge(inside) if inside.geom_type == "MultiLineString" else inside
    parts = list(getattr(merged, "geoms", [merged]))
    total = sum(p.length for p in parts)
    pts = []
    for k in range(n):
        target = (k + 0.5) / n * total
        for p in parts:
            if target <= p.length:
                q = p.interpolate(target)
                pts.append(tuple(round(v, 6) for v in to_lonlat(q.x, q.y)))
                break
            target -= p.length
    return pts


def scenario_grid(net: Network, n_points: int = 10,
                  winds: tuple[float, ...] = tuple(range(0, 360, 45)),
                  wind_speeds: tuple[float, ...] = (1.5,),
                  times: tuple[str, ...] = ("night", "day", "gameday"),
                  compliances: tuple[float, ...] = (0.85,),
                  chemicals: tuple[str, ...] = ("chlorine",),
                  spill_sizes: tuple[str, ...] = ("large",),
                  random_closures: int = 0, seed: int = 0,
                  max_from_center_m: float = 2500.0) -> pd.DataFrame:
    """Cartesian grid of scenarios. Default: 10 points × 8 winds × 3 times = 240 scenarios.

    Derailment points stay within max_from_center_m of the study-area center (the isthmus core),
    even though the road network extends farther out so evacuees have real exits.
    """
    rng = np.random.default_rng(seed)
    major = [d["edge_id"] for _, _, d in net.G.edges(data=True) if d["road_class"] in A.CONTRAFLOW_CLASSES]
    rows = []
    for sid, ((lon, lat), w, ws, tod, c, chem, size) in enumerate(itertools.product(
            release_points(net, n_points, max_from_center_m), winds, wind_speeds, times, compliances, chemicals, spill_sizes)):
        closed = tuple(int(e) for e in rng.choice(major, size=min(random_closures, len(major)), replace=False)) \
            if random_closures and major else ()
        rows.append(dict(scenario_id=sid, release_lon=lon, release_lat=lat, chemical=chem, spill_size=size,
                         wind_from_deg=float(w), wind_speed_mps=float(ws), time_of_day=tod, compliance=float(c),
                         bus_count=20, bus_capacity=60, contraflow=False, closed_edge_ids=json.dumps(list(closed)),
                         seed=sid))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- run

def _params(row) -> ScenarioParams:
    closed = row["closed_edge_ids"]
    closed = tuple(json.loads(closed)) if isinstance(closed, str) else tuple(closed or ())
    return ScenarioParams(
        release_lon=float(row["release_lon"]), release_lat=float(row["release_lat"]),
        chemical=row["chemical"], spill_size=row["spill_size"], wind_from_deg=float(row["wind_from_deg"]),
        wind_speed_mps=float(row["wind_speed_mps"]), time_of_day=row["time_of_day"],
        compliance=float(row["compliance"]), bus_count=int(row["bus_count"]), bus_capacity=int(row["bus_capacity"]),
        contraflow=bool(row["contraflow"]), closed_edge_ids=closed, seed=int(row.get("seed", 0)))


def run_row(row, net: Network, bus_time_limit_s: float = 0.3) -> dict:
    """Run one grid row → one flat result dict (RESULT_SCHEMA columns). Errors are captured, not raised."""
    A.BUS_SOLVER_TIME_LIMIT_S = bus_time_limit_s
    p = _params(row)
    out = dict(scenario_id=int(row["scenario_id"]), release_lon=p.release_lon, release_lat=p.release_lat,
               chemical=p.chemical, spill_size=p.spill_size, wind_from_deg=p.wind_from_deg,
               wind_speed_mps=p.wind_speed_mps, time_of_day=p.time_of_day, compliance=p.compliance,
               bus_count=p.bus_count, contraflow=p.contraflow, n_closed=len(p.closed_edge_ids), error=None)
    try:
        r, d = run_with_diagnostics(p, net)
    except Exception as exc:  # one bad scenario must not kill a 500-scenario job
        out.update(error=f"{type(exc).__name__}: {exc}")
        for k in ("clearance_time_s", "sim_clearance_s", "people_evacuating", "people_sheltering",
                  "need_bus_total", "need_bus_unserved", "runtime_ms"):
            out[k] = math.nan
        out.update(vehicles=0, n_evacuate=0, n_shelter=0, bottleneck_edge_ids="[]", shelter_block_ids="[]",
                   evacuate_block_ids="[]", facilities_in_zone="[]")
        return out
    s = r.summary
    hz_fac = []
    if not net.facilities.empty:
        from engine.hazard import build_hazard
        hz = build_hazard(net, p.release_lon, p.release_lat, p.chemical, p.spill_size, p.time_of_day,
                          p.wind_from_deg, p.wind_speed_mps)
        inside = hz.in_zone(net.facilities["x"].to_numpy(), net.facilities["y"].to_numpy())
        hz_fac = net.facilities.loc[inside, "facility_id"].astype(str).tolist()
    out.update(
        clearance_time_s=s.clearance_time_s, sim_clearance_s=d.sim_clearance_s,
        people_evacuating=s.people_evacuating, people_sheltering=s.people_sheltering,
        need_bus_total=s.need_bus_total, need_bus_unserved=s.need_bus_unserved, vehicles=int(d.vehicles),
        n_evacuate=sum(b.decision == "evacuate" for b in r.blocks),
        n_shelter=sum(b.decision == "shelter" for b in r.blocks),
        runtime_ms=s.runtime_ms,
        bottleneck_edge_ids=json.dumps(s.bottleneck_edge_ids),
        shelter_block_ids=json.dumps([b.block_id for b in r.blocks if b.decision == "shelter"]),
        evacuate_block_ids=json.dumps([b.block_id for b in r.blocks if b.decision == "evacuate"]),
        facilities_in_zone=json.dumps(hz_fac),
    )
    return out


_NET_CACHE: dict[str, Network] = {}


def run_partition(pdf: pd.DataFrame, data_dir: str) -> pd.DataFrame:
    """applyInPandas entry point. Loads the network once per worker process and reuses it."""
    if data_dir not in _NET_CACHE:
        _NET_CACHE[data_dir] = load_network(data_dir, use_cache=False)
    net = _NET_CACHE[data_dir]
    cols = [c.split()[0] for c in RESULT_SCHEMA.split(", ")]
    return pd.DataFrame([run_row(row, net) for _, row in pdf.iterrows()], columns=cols)


def _worker_init(data_dir: str):
    _NET_CACHE[data_dir] = load_network(data_dir)


def _worker_run(args):
    row, data_dir = args
    return run_row(row, _NET_CACHE[data_dir])


def run_local(grid: pd.DataFrame, data_dir: str, workers: int | None = None) -> pd.DataFrame:
    """Run a grid on this machine with a process pool (for testing before Databricks)."""
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    rows = [r for _, r in grid.iterrows()]
    if workers == 1:
        net = load_network(data_dir)
        return pd.DataFrame([run_row(r, net) for r in rows])
    with ProcessPoolExecutor(workers, initializer=_worker_init, initargs=(data_dir,)) as ex:
        return pd.DataFrame(list(ex.map(_worker_run, [(r, data_dir) for r in rows], chunksize=4)))


# --------------------------------------------------------------------------- gold

def gold_tables(results: pd.DataFrame, net: Network, top_n: int = 10) -> dict:
    ok = results[results["error"].isna()] if "error" in results else results
    n = len(ok)
    edge_meta = {d["edge_id"]: (d.get("name"), d["road_class"]) for _, _, d in net.G.edges(data=True)}

    # bottlenecks by road name (a road is many edges); keep the most frequent edge for map highlighting
    road_scen: Counter = Counter()
    road_edge: dict[str, Counter] = defaultdict(Counter)
    for ids in ok["bottleneck_edge_ids"]:
        seen = set()
        for e in json.loads(ids):
            name, cls = edge_meta.get(e, (None, "road"))
            key = name or f"Unnamed {cls}"
            road_edge[key][e] += 1
            seen.add(key)
        road_scen.update(seen)
    top_bottlenecks = [{"edge_id": int(road_edge[k].most_common(1)[0][0]), "name": k, "times_bottleneck": int(c),
                        "share": round(c / n, 3) if n else 0.0}
                       for k, c in road_scen.most_common(top_n)]

    fac_count: Counter = Counter()
    for ids in ok["facilities_in_zone"]:
        fac_count.update(set(json.loads(ids)))
    fmeta = net.facilities.set_index("facility_id") if not net.facilities.empty else pd.DataFrame()
    facilities_in_zone = [{"facility_id": f, "name": str(fmeta.at[f, "name"]) if f in fmeta.index else f,
                           "type": str(fmeta.at[f, "type"]) if f in fmeta.index else "facility",
                           "share": round(c / n, 3)} for f, c in fac_count.most_common(top_n)]

    ww = ok.groupby("wind_from_deg").agg(mean_clearance_s=("sim_clearance_s", "mean"),
                                         mean_unserved=("need_bus_unserved", "mean"),
                                         n=("scenario_id", "count")).reset_index()
    worst_wind = [{"wind_from_deg": float(r.wind_from_deg), "mean_clearance_s": round(float(r.mean_clearance_s), 1),
                   "mean_unserved": round(float(r.mean_unserved), 1), "n": int(r.n)}
                  for r in ww.sort_values("mean_clearance_s", ascending=False).itertuples()]

    by_time = ok.groupby("time_of_day").agg(mean_clearance_s=("sim_clearance_s", "mean"),
                                            mean_evacuating=("people_evacuating", "mean"),
                                            mean_sheltering=("people_sheltering", "mean"),
                                            mean_unserved=("need_bus_unserved", "mean")).round(1).reset_index()

    shelter_c, evac_c = Counter(), Counter()
    for a, b in zip(ok["shelter_block_ids"], ok["evacuate_block_ids"]):
        shelter_c.update(json.loads(a))
        evac_c.update(json.loads(b))
    block_freq = pd.DataFrame({"block_id": net.blocks["block_id"]})
    block_freq["share_shelter"] = block_freq["block_id"].map(lambda b: shelter_c[b] / n if n else 0.0).round(3)
    block_freq["share_evacuate"] = block_freq["block_id"].map(lambda b: evac_c[b] / n if n else 0.0).round(3)

    insights = {
        "source": "gold", "n_scenarios": int(n), "n_failed": int(len(results) - n),
        "top_bottlenecks": top_bottlenecks, "facilities_in_zone": facilities_in_zone, "worst_wind": worst_wind,
        "by_time_of_day": by_time.to_dict("records"),
        "median_runtime_ms": float(ok["runtime_ms"].median()) if n else None,
    }
    return {"insights": insights, "block_frequency": block_freq}


def export_gold_json(gold: dict, out_dir: str | Path) -> Path:
    """Write data/gold/insights.json (what the backend's /insights serves) + block_frequency.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "insights.json").write_text(json.dumps(gold["insights"], indent=1))
    gold["block_frequency"].to_json(out / "block_frequency.json", orient="records")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a scenario grid locally and write gold JSON.")
    ap.add_argument("data_dir")
    ap.add_argument("--n-points", type=int, default=8)
    ap.add_argument("--wind-speed", type=float, default=1.5)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default="data/gold")
    ap.add_argument("--results", default=None, help="optional parquet path for raw per-scenario results")
    a = ap.parse_args()
    net = load_network(a.data_dir)
    grid = scenario_grid(net, n_points=a.n_points, wind_speeds=(a.wind_speed,))
    print(f"running {len(grid)} scenarios …")
    t0 = time.time()
    res = run_local(grid, a.data_dir, a.workers)
    print(f"done in {time.time() - t0:.0f}s, {res['error'].notna().sum()} failed")
    if a.results:
        res.to_parquet(a.results, index=False)
    gold = gold_tables(res, net)
    print("wrote", export_gold_json(gold, a.out))
    for b in gold["insights"]["top_bottlenecks"][:8]:
        print(f"  {b['name']:32s} {b['share'] * 100:4.0f}% of scenarios")


if __name__ == "__main__":
    main()
