"""Starter pipeline: real Madison silver tables from OpenStreetMap + 2020 Census blocks.

    python data/build_silver_osm.py data/silver

Downloads are cached in cache/osm/ (git-ignored), so reruns are fast.

REAL:  roads, rail lines, bus stops (OSM via OSMnx); block population + housing units (Census 2020,
       TIGERweb — no API key needed).
TODO (marked PLACEHOLDER below — Person 2 replaces these):
  - ACS shares (zero-vehicle, disability, 65+): constants → ACS 5-year block groups (needs Census API key)
  - pop_day: copy of pop_night → LEHD LODES (add in-workers, subtract out-commuters)
  - nursing homes: OSM (only ~1 tagged) → CMS Provider Data, beds = residents
  - bus garage + shelter: made-up points → real Madison Metro garage + a real shelter outside the isthmus
  - erg_distances: not written → engine falls back to engine/assumptions.py ERG_FALLBACK
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import requests
import shapely

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "cache" / "osm"
BBOX = (-89.43, 43.05, -89.33, 43.10)          # west, south, east north — isthmus + downtown + Camp Randall
CAMP_RANDALL = (-89.4127, 43.0700)
GAMEDAY_CROWD = 75_000

# ---- PLACEHOLDERS — replace with real data -------------------------------------------------------------
PLACEHOLDER_ZERO_VEHICLE = 0.25
PLACEHOLDER_DISABILITY = 0.10
PLACEHOLDER_AGE65 = 0.10
PLACEHOLDER_NURSING_RESIDENTS = 60
PLACEHOLDER_HOSPITAL_RESIDENTS = 200
PLACEHOLDER_DEPOTS = [
    {"depot_id": "garage_test", "kind": "bus_garage", "name": "TEST garage (east)", "lon": -89.355, "lat": 43.095},
    {"depot_id": "shelter_test", "kind": "shelter", "name": "TEST shelter (west)", "lon": -89.428, "lat": 43.075},
]
# --------------------------------------------------------------------------------------------------------


def cached_graph():
    path = CACHE / "drive.graphml"
    if path.exists():
        return ox.load_graphml(path)
    print("downloading OSM drive network …")
    G = ox.graph_from_bbox(BBOX, network_type="drive", simplify=True)
    ox.save_graphml(G, path)
    return G


def cached_features(name: str, tags: dict) -> gpd.GeoDataFrame:
    path = CACHE / f"{name}.parquet"
    if path.exists():
        return gpd.read_parquet(path)
    print(f"downloading OSM {name} …")
    try:
        f = ox.features_from_bbox(BBOX, tags=tags).reset_index()
    except ox._errors.InsufficientResponseError:          # genuinely nothing tagged → cache the empty result
        f = gpd.GeoDataFrame(geometry=[], crs=4326)
    except Exception as exc:                              # server/network error → don't cache, try next run
        print(f"  download failed ({exc.__class__.__name__}) — rerun later; continuing without {name}")
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    keep = [c for c in ("name", "operator", "amenity", "social_facility", "railway", "highway") if c in f]
    f = gpd.GeoDataFrame(f[keep].astype("string"), geometry=f.geometry, crs=4326)
    f.to_parquet(path)
    return f


def cached_census_blocks() -> gpd.GeoDataFrame:
    path = CACHE / "census_blocks.parquet"
    if path.exists():
        return gpd.read_parquet(path)
    print("downloading 2020 Census blocks (TIGERweb) …")
    url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10/query"
    feats, off = [], 0
    while True:
        p = dict(geometry=",".join(map(str, BBOX)), geometryType="esriGeometryEnvelope", inSR=4326,
                 spatialRel="esriSpatialRelIntersects", outFields="GEOID,POP100,HU100", returnGeometry="true",
                 outSR=4326, f="geojson", resultOffset=off, resultRecordCount=1000)
        fs = requests.get(url, params=p, timeout=120).json().get("features", [])
        feats += fs
        if len(fs) < 1000:
            break
        off += 1000
    g = gpd.GeoDataFrame.from_features(feats, crs=4326)
    g.to_parquet(path)
    return g


def first(v):
    if isinstance(v, (list, tuple, np.ndarray)):
        return v[0] if len(v) else None
    if isinstance(v, str) and v.startswith("["):
        return v.strip("[]").split(",")[0].strip(" '\"")
    return v


def speed_kph(v):
    v = first(v)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    m = re.search(r"(\d+(?:\.\d+)?)", str(v))
    if not m:
        return np.nan
    x = float(m.group(1))
    return x * 1.609 if "mph" in str(v) or x <= 70 else x     # US OSM speeds are mph


def lanes_per_direction(v, oneway: bool):
    v = first(v)
    try:
        n = float(str(v).split(";")[0])
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(n):
        return np.nan
    return max(1, round(n if oneway else n / 2))              # OSM lanes = both directions on two-way roads


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    G = cached_graph()
    nodes, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()
    nid = nodes.index.to_numpy()
    k = np.cos(np.radians(43.07))
    nxy = np.column_stack([nodes.geometry.x.to_numpy() * k, nodes.geometry.y.to_numpy()])

    def nearest(lons, lats) -> np.ndarray:
        pts = np.column_stack([np.atleast_1d(np.asarray(lons, float)) * k, np.atleast_1d(np.asarray(lats, float))])
        return np.array([nid[np.argmin(((nxy - p) ** 2).sum(1))] for p in pts], dtype="int64")

    # ---- road_nodes: exits = nodes within 150 m of the study-area edge
    west, south, east, north = BBOX
    x, y = nodes.geometry.x, nodes.geometry.y
    dlon, dlat = 150 / 81_400, 150 / 111_000
    is_exit = (x < west + dlon) | (x > east - dlon) | (y < south + dlat) | (y > north - dlat)
    road_nodes = pd.DataFrame({"node_id": nid.astype("int64"), "lon": x.values, "lat": y.values,
                               "is_exit": is_exit.values})
    road_nodes.to_parquet(out / "road_nodes.parquet", index=False)

    # ---- road_edges (missing lanes/speed left NaN — the engine fills them by road class)
    oneway = edges["oneway"].fillna(False).astype(bool)
    lanes_col = edges["lanes"] if "lanes" in edges else pd.Series([None] * len(edges))
    road_edges = gpd.GeoDataFrame({
        "edge_id": np.arange(1, len(edges) + 1, dtype="int64"),
        "u": edges["u"].astype("int64"), "v": edges["v"].astype("int64"),
        "length_m": edges["length"].astype(float),                       # OSMnx geodesic length
        "speed_kph": edges["maxspeed"].map(speed_kph) if "maxspeed" in edges else np.nan,
        "lanes": [lanes_per_direction(l, o) for l, o in zip(lanes_col, oneway)],
        "road_class": edges["highway"].map(first).astype(str),
        "capacity_vph": np.nan,
        "name": edges["name"].map(first) if "name" in edges else None,
    }, geometry=edges.geometry.values, crs=4326)
    road_edges.to_parquet(out / "road_edges.parquet", index=False)

    # ---- blocks: real 2020 population; ACS shares are PLACEHOLDERS
    cb = cached_census_blocks()
    cb = cb[cb["POP100"] > 0].copy()
    rep = cb.geometry.representative_point()
    pop = cb["POP100"].astype(float)
    blocks = gpd.GeoDataFrame({
        "block_id": cb["GEOID"].astype(str),
        "node_id": nearest(rep.x.values, rep.y.values),
        "pop_night": pop,
        "pop_day": pop,                                   # PLACEHOLDER → LODES
        "pop_gameday": pop,
        "households": cb["HU100"].astype(float) * 0.93,   # occupied ≈ 93% of housing units
        "zero_vehicle_share": PLACEHOLDER_ZERO_VEHICLE,
        "disability_share": PLACEHOLDER_DISABILITY,
        "age65_share": PLACEHOLDER_AGE65,
    }, geometry=cb.geometry.values, crs=4326).reset_index(drop=True)
    d = blocks.geometry.representative_point().distance(shapely.Point(*CAMP_RANDALL))
    near = d.nsmallest(5).index
    blocks.loc[near, "pop_gameday"] = blocks.loc[near, "pop_day"] + GAMEDAY_CROWD / len(near)
    blocks.to_parquet(out / "blocks.parquet", index=False)

    # ---- facilities (OSM — replace nursing homes with CMS)
    rows = []
    for kind, tags, res in (("nursing_home", {"social_facility": "nursing_home", "amenity": "nursing_home"},
                             PLACEHOLDER_NURSING_RESIDENTS),
                            ("hospital", {"amenity": "hospital"}, PLACEHOLDER_HOSPITAL_RESIDENTS)):
        f = cached_features(kind, tags)
        for i, r in f.iterrows():
            if kind == "nursing_home" and not ((r.get("social_facility") == "nursing_home") or
                                               (r.get("amenity") == "nursing_home")):
                continue
            p = r.geometry.representative_point()
            rows.append({"facility_id": f"{kind}_{i}", "type": kind, "name": r.get("name") or kind,
                         "node_id": 0, "residents": float(res), "lon": p.x, "lat": p.y})
    fac = pd.DataFrame(rows, columns=["facility_id", "type", "name", "node_id", "residents", "lon", "lat"])
    if len(fac):
        fac["node_id"] = nearest(fac["lon"], fac["lat"])
    fac.astype({"node_id": "int64"}).to_parquet(out / "facilities.parquet", index=False)

    # ---- pickup points: OSM bus stops + nursing-home doors
    stops = cached_features("bus_stops", {"highway": "bus_stop"})
    sp = stops.geometry.representative_point()
    pk = pd.DataFrame({"pickup_id": [f"stop_{i}" for i in range(len(stops))], "kind": "metro_stop",
                       "node_id": nearest(sp.x, sp.y) if len(stops) else np.array([], "int64"),
                       "lon": sp.x.values, "lat": sp.y.values})
    nh = fac[fac["type"] == "nursing_home"]
    pk = pd.concat([pk, pd.DataFrame({"pickup_id": nh["facility_id"], "kind": "facility",
                                      "node_id": nh["node_id"], "lon": nh["lon"], "lat": nh["lat"]})],
                   ignore_index=True)
    pk.astype({"node_id": "int64"}).to_parquet(out / "pickup_points.parquet", index=False)

    # ---- depots (PLACEHOLDER locations)
    dep = pd.DataFrame(PLACEHOLDER_DEPOTS)
    dep["node_id"] = nearest(dep["lon"], dep["lat"])
    dep[["depot_id", "kind", "name", "node_id", "lon", "lat"]].to_parquet(out / "depots.parquet", index=False)

    # ---- rail lines
    rails = cached_features("rails", {"railway": "rail"})
    rails = rails[rails.geometry.geom_type == "LineString"].reset_index(drop=True)
    gpd.GeoDataFrame({"rail_id": np.arange(1, len(rails) + 1, dtype="int64"),
                      "name": rails["name"] if "name" in rails else None},
                     geometry=rails.geometry.values, crs=4326).to_parquet(out / "rail_lines.parquet", index=False)

    # ---- ERG distances: PLACEHOLDER copy of the engine's fallback — replace with real ERG Table 1 values
    sys.path.insert(0, str(REPO))
    from engine.assumptions import ERG_FALLBACK
    pd.DataFrame([{"chemical": c, "spill_size": s, "time_of_day": t, "isolation_m": float(i), "protect_m": float(p)}
                  for (c, s, t), (i, p) in ERG_FALLBACK.items()]).to_parquet(out / "erg_distances.parquet", index=False)

    print(f"wrote {out}:{len(road_nodes)} nodes, {len(road_edges)} edges, {len(blocks)} blocks "
          f"({int(blocks.pop_night.sum()):,} people), {len(fac)} facilities, {len(pk)} pickups, {len(rails)} rail segs")
    print(f"missing lanes {int(road_edges.lanes.isna().sum())}, missing speed {int(road_edges.speed_kph.isna().sum())}"
          f" of {len(road_edges)} edges (engine fills by road class)")
    print("PLACEHOLDERS still in use: ACS shares, pop_day, nursing-home residents, depots, ERG table")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO / "data" / "silver"))
