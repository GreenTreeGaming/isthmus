"""A small synthetic isthmus-like grid in the silver schema, so the engine never waits on real data.

Used by tests and run_demo.py. Real data replaces it via data/silver/ or data/fixtures/.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import shapely

LON0, LAT0 = -89.395, 43.065
DLON, DLAT = 0.0031, 0.00225   # ≈ 250 m spacing at Madison's latitude
NX, NY = 12, 9
ARTERIAL_ROW = 4               # E–W primary (think E Washington)
ARTERIAL_COL = 6               # N–S secondary


def _nid(i: int, j: int) -> int:
    return 1000 + j * NX + i


def _lonlat(i: int, j: int) -> tuple[float, float]:
    return LON0 + i * DLON, LAT0 + j * DLAT


def make_tables(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)

    nodes = []
    for j in range(NY):
        for i in range(NX):
            lon, lat = _lonlat(i, j)
            nodes.append({"node_id": _nid(i, j), "lon": lon, "lat": lat,
                          "is_exit": i in (0, NX - 1) or j in (0, NY - 1)})
    nodes = pd.DataFrame(nodes)

    edges, eid = [], 1

    def add(a, b, cls, lanes, speed, name):
        nonlocal eid
        (ia, ja), (ib, jb) = a, b
        la, lb = _lonlat(ia, ja), _lonlat(ib, jb)
        for (u, v, p, q) in ((_nid(ia, ja), _nid(ib, jb), la, lb), (_nid(ib, jb), _nid(ia, ja), lb, la)):
            edges.append({
                "edge_id": eid, "u": u, "v": v, "length_m": 250.0, "speed_kph": speed, "lanes": lanes,
                "road_class": cls, "capacity_vph": np.nan, "name": name,
                "geometry": shapely.to_wkb(shapely.LineString([p, q])),
            })
            eid += 1

    for j in range(NY):
        for i in range(NX - 1):
            if j == ARTERIAL_ROW:
                add((i, j), (i + 1, j), "primary", 2, 56, "Arterial Ave")
            else:
                add((i, j), (i + 1, j), "residential", 1, 40, f"Street {j}")
    for i in range(NX):
        for j in range(NY - 1):
            if i == ARTERIAL_COL:
                add((i, j), (i, j + 1), "secondary", 1, 48, "Center St")
            else:
                add((i, j), (i, j + 1), "residential", 1, 40, f"Avenue {i}")
    edges = pd.DataFrame(edges)
    edges.loc[edges.index % 7 == 0, ["speed_kph", "lanes"]] = np.nan  # exercise default filling

    blocks = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            (lo0, la0), (lo1, la1) = _lonlat(i, j), _lonlat(i + 1, j + 1)
            pop = float(rng.integers(150, 600))
            blocks.append({
                "block_id": f"55025{j:04d}{i:06d}",
                "node_id": _nid(i, j),
                "pop_night": pop,
                "pop_day": pop * float(rng.uniform(0.6, 1.6)),
                "pop_gameday": pop * float(rng.uniform(0.6, 1.6)),
                "households": pop / 2.2,
                "zero_vehicle_share": float(rng.uniform(0.05, 0.45)),
                "disability_share": float(rng.uniform(0.03, 0.15)),
                "age65_share": float(rng.uniform(0.03, 0.25)),
                "geometry": shapely.to_wkb(shapely.box(lo0, la0, lo1, la1)),
            })
    blocks = pd.DataFrame(blocks)
    # stadium crowd on one block for game day
    blocks.loc[(blocks.index == 15), "pop_gameday"] += 20_000

    def fac(fid, typ, name, i, j, residents):
        lon, lat = _lonlat(i, j)
        return {"facility_id": fid, "type": typ, "name": name, "node_id": _nid(i, j),
                "residents": residents, "lon": lon, "lat": lat}

    facilities = pd.DataFrame([
        fac("nh_01", "nursing_home", "Lakeview Senior Living", 7, 5, 80),
        fac("nh_02", "nursing_home", "Capitol Care Center", 4, 3, 45),
        fac("hosp_01", "hospital", "Downtown Hospital", 5, 6, 200),
        fac("stadium_01", "stadium", "Stadium", 4, 1, 0),
    ])

    pickups = []
    for k, (i, j) in enumerate([(2, 2), (5, 2), (8, 2), (2, 5), (5, 5), (9, 6), (3, 7), (8, 7)]):
        lon, lat = _lonlat(i, j)
        pickups.append({"pickup_id": f"stop_{k}", "kind": "metro_stop", "node_id": _nid(i, j), "lon": lon, "lat": lat})
    for f in facilities[facilities["type"] == "nursing_home"].itertuples():
        pickups.append({"pickup_id": f.facility_id, "kind": "facility", "node_id": f.node_id, "lon": f.lon, "lat": f.lat})
    pickups = pd.DataFrame(pickups)

    g_lon, g_lat = _lonlat(0, 0)
    s_lon, s_lat = _lonlat(NX - 1, NY - 1)
    depots = pd.DataFrame([
        {"depot_id": "garage_main", "kind": "bus_garage", "name": "Metro Garage", "node_id": _nid(0, 0), "lon": g_lon, "lat": g_lat},
        {"depot_id": "shelter_east", "kind": "shelter", "name": "East Shelter", "node_id": _nid(NX - 1, NY - 1), "lon": s_lon, "lat": s_lat},
    ])

    rail = shapely.LineString([_lonlat(0, 1), _lonlat(NX - 1, NY - 2)])
    rail_lines = pd.DataFrame([{"rail_id": 1, "name": "Test Rail", "geometry": shapely.to_wkb(rail)}])

    erg = pd.DataFrame([
        {"chemical": "chlorine", "spill_size": "small", "time_of_day": "day", "isolation_m": 60, "protect_m": 300},
        {"chemical": "chlorine", "spill_size": "small", "time_of_day": "night", "isolation_m": 60, "protect_m": 1100},
        {"chemical": "chlorine", "spill_size": "large", "time_of_day": "day", "isolation_m": 500, "protect_m": 1500},
        {"chemical": "chlorine", "spill_size": "large", "time_of_day": "night", "isolation_m": 500, "protect_m": 2500},
        {"chemical": "ammonia", "spill_size": "small", "time_of_day": "day", "isolation_m": 30, "protect_m": 100},
        {"chemical": "ammonia", "spill_size": "small", "time_of_day": "night", "isolation_m": 30, "protect_m": 200},
        {"chemical": "ammonia", "spill_size": "large", "time_of_day": "day", "isolation_m": 150, "protect_m": 800},
        {"chemical": "ammonia", "spill_size": "large", "time_of_day": "night", "isolation_m": 150, "protect_m": 2000},
    ])
    # NOTE: synthetic grid is ~3 km wide, so "large" protect distances are scaled down to fit it.

    return {
        "road_nodes": nodes, "road_edges": edges, "blocks": blocks, "facilities": facilities,
        "pickup_points": pickups, "depots": depots, "rail_lines": rail_lines, "erg_distances": erg,
    }


def write_synthetic(out_dir: str | Path, seed: int = 7) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in make_tables(seed).items():
        df.to_parquet(out / f"{name}.parquet", index=False)
    return out


def center_release() -> tuple[float, float]:
    """A point on the synthetic rail line near the middle of the grid."""
    return _lonlat(4, 3)
