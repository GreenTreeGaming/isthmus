"""Robustness check: do the headline findings survive when our biggest assumptions change?

    python -m engine.robustness data/silver --out data/gold/robustness.json

Runs the same scenario grid under several assumption variants and compares the findings judges will hear:
clearance by wind speed, the share of scenarios each facility is in the zone, the Metro garage in the zone,
how many bus riders go unserved, and whether the top choke-point roads stay the same.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from engine import assumptions as A
from engine.batch import _NET_CACHE, gold_tables, run_row, scenario_grid
from engine.network import load_network

LANE_KEYS = ("LANE_CAPACITY_VPH",)

VARIANTS: dict[str, dict] = {
    "baseline": {},
    "compliance 60%": {"compliance": 0.60},
    "compliance 100%": {"compliance": 1.00},
    "road capacity −25%": {"capacity_scale": 0.75},
    "road capacity +25%": {"capacity_scale": 1.25},
    "warning takes 15 min (not 5)": {"MOBILIZATION_S": 900},
    "buses leave after 20 min (not 10)": {"BUS_DISPATCH_DELAY_S": 1200},
}


def _apply(overrides: dict) -> None:
    for k, v in overrides.items():
        if k == "capacity_scale":
            A.LANE_CAPACITY_VPH = {c: x * v for c, x in A.LANE_CAPACITY_VPH.items()}
            A.LINK_CAPACITY_VPH *= v
            A.DEFAULT_LANE_CAPACITY_VPH *= v
        elif k != "compliance":
            setattr(A, k, v)


def _init(data_dir: str, overrides: dict) -> None:
    _apply(overrides)
    net = load_network(data_dir)
    if "capacity_scale" in overrides:          # capacities are baked into edges at load time
        s = overrides["capacity_scale"]
        for _, _, d in net.G.edges(data=True):
            d["capacity_vph"] *= s
    _NET_CACHE[data_dir] = net


def _run(args):
    row, data_dir = args
    return run_row(row, _NET_CACHE[data_dir])


def run_variant(grid: pd.DataFrame, data_dir: str, overrides: dict, workers: int) -> pd.DataFrame:
    g = grid.copy()
    if "compliance" in overrides:
        g["compliance"] = overrides["compliance"]
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(data_dir, overrides)) as ex:
        return pd.DataFrame(list(ex.map(_run, [(r, data_dir) for _, r in g.iterrows()], chunksize=4)))


def summarize(res: pd.DataFrame, net) -> dict:
    gold = gold_tables(res, net)["insights"]
    ok = res[res["error"].isna()]
    return {
        "n": int(len(ok)), "failed": int(res["error"].notna().sum()),
        "clearance_min_by_wind_speed": {str(r["wind_speed_mps"]): round(r["mean_clearance_s"] / 60, 1)
                                        for r in gold["by_wind_speed"]},
        "mean_clearance_min": round(float(ok["sim_clearance_s"].mean()) / 60, 1),
        "mean_evacuating": round(float(ok["people_evacuating"].mean())),
        "mean_unserved": round(float(ok["need_bus_unserved"].mean()), 1),
        "capitol_lakes_in_zone": next((f["share"] for f in gold["facilities_in_zone"]
                                       if "Capitol Lakes" in f["name"]), None),
        "garage_in_zone": gold["garage_in_zone_share"],
        "top_choke_points": [b["name"] for b in gold["top_bottlenecks"][:5]],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--n-points", type=int, default=6)
    ap.add_argument("--out", default="data/gold/robustness.json")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    net = load_network(a.data_dir)
    grid = scenario_grid(net, n_points=a.n_points, times=("day", "night"))
    print(f"{len(grid)} scenarios × {len(VARIANTS)} variants")
    out = {"grid": {"n_scenarios": len(grid), "n_points": a.n_points, "times": ["day", "night"],
                    "wind_speeds": sorted(grid["wind_speed_mps"].unique().tolist())}, "variants": {}}
    for name, ov in VARIANTS.items():
        t0 = time.time()
        res = run_variant(grid, a.data_dir, ov, a.workers)
        out["variants"][name] = summarize(res, net)
        s = out["variants"][name]
        print(f"{name:34s} {time.time() - t0:5.0f}s  clear {s['mean_clearance_min']:5.1f} min  "
              f"by wind {s['clearance_min_by_wind_speed']}  unserved {s['mean_unserved']}  "
              f"CapLakes {s['capitol_lakes_in_zone']}  garage {s['garage_in_zone']}  top {s['top_choke_points'][:3]}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
