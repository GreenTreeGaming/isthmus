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
BBOX = (-89.47, 43.015, -89.29, 43.125)        # west, south, east, north — isthmus + downtown + Camp Randall, out to the Beltline
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


def census_key() -> str | None:
    """CENSUS_API_KEY from the environment or the repo's git-ignored .env file."""
    import os
    if os.environ.get("CENSUS_API_KEY"):
        return os.environ["CENSUS_API_KEY"].strip()
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("CENSUS_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


MAX_DAY_DENSITY_PER_KM2 = 100_000      # dense office district; above the 99th percentile of Madison blocks


def lodes_day_population(block_ids: pd.Series, pop_night: pd.Series, area_km2: pd.Series) -> pd.Series:
    """LEHD LODES 2022: daytime = residents − employed residents (leave for work) + jobs located in the block.

    Students are not workers in LODES, so campus daytime population is understated (stated limitation).
    """
    def load(kind: str, col: str) -> pd.Series:
        fname = f"wi_{kind}_S000_JT00_2022.csv.gz"
        path = CACHE / fname
        if not path.exists():
            print(f"downloading LODES {kind} …")
            r = requests.get(f"https://lehd.ces.census.gov/data/lodes/LODES8/wi/{kind}/{fname}", timeout=300)
            r.raise_for_status()
            path.write_bytes(r.content)
        df = pd.read_csv(path, usecols=[col, "C000"], dtype={col: str})
        return df.set_index(col)["C000"].astype(float)

    jobs = load("wac", "w_geocode")
    workers = load("rac", "h_geocode")
    ids = block_ids.astype(str)
    day = pop_night.to_numpy() - ids.map(workers).fillna(0).to_numpy() + ids.map(jobs).fillna(0).to_numpy()
    day = np.maximum(day, 0.0)
    # LODES puts every job of some big employers at one HQ block (UW–Madison ≈ 22k jobs on one campus block,
    # State of Wisconsin at the Capitol). Cap daytime density so one block doesn't hold a stadium's worth of cars.
    cap = np.maximum(pop_night.to_numpy(), area_km2.to_numpy() * MAX_DAY_DENSITY_PER_KM2)
    capped = day > cap
    if capped.any():
        print(f"LODES: capped {int(capped.sum())} HQ-artifact blocks, removed {int((day - cap)[capped].sum()):,} people")
    return pd.Series(np.minimum(day, cap), index=block_ids.index)


def cms_nursing_homes() -> pd.DataFrame:
    """CMS Provider Data (certified nursing homes) in Madison; residents = average residents per day."""
    path = CACHE / "cms_madison.json"
    if path.exists():
        rows = pd.read_json(path)
    else:
        print("downloading CMS nursing homes …")
        url = "https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0"
        p = {"conditions[0][property]": "state", "conditions[0][value]": "WI",
             "conditions[1][property]": "citytown", "conditions[1][value]": "MADISON", "limit": 500}
        rows = pd.DataFrame(requests.get(url, params=p, timeout=120).json().get("results", []))
        rows.to_json(path, orient="records")
    if rows.empty:
        return rows
    w, s, e, n = BBOX
    rows["lat"] = pd.to_numeric(rows["latitude"], errors="coerce")
    rows["lon"] = pd.to_numeric(rows["longitude"], errors="coerce")
    rows = rows[(rows.lon >= w) & (rows.lon <= e) & (rows.lat >= s) & (rows.lat <= n)].copy()
    res = pd.to_numeric(rows["average_number_of_residents_per_day"], errors="coerce")
    beds = pd.to_numeric(rows["number_of_certified_beds"], errors="coerce")
    rows["residents"] = res.fillna(beds).fillna(PLACEHOLDER_NURSING_RESIDENTS)
    return rows.rename(columns={"provider_name": "name", "cms_certification_number_ccn": "ccn"})


def acs_shares(key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ACS 2022 5-year, Dane County. Vehicles + age at block group; disability at tract (not published at BG)."""
    path_bg, path_tr = CACHE / "acs_bg.parquet", CACHE / "acs_tract.parquet"
    if path_bg.exists() and path_tr.exists():
        return pd.read_parquet(path_bg), pd.read_parquet(path_tr)
    api = "https://api.census.gov/data/2022/acs/acs5"

    def get(vars_, geo, within):
        r = requests.get(api, params={"get": ",".join(vars_), "for": geo, "in": within, "key": key}, timeout=120)
        r.raise_for_status()
        j = r.json()
        df = pd.DataFrame(j[1:], columns=j[0])
        for v in vars_:
            df[v] = pd.to_numeric(df[v], errors="coerce").clip(lower=0)
        return df

    age = ["B01001_001E"] + [f"B01001_{i:03d}E" for i in [*range(20, 26), *range(44, 50)]]
    veh = ["B25044_001E", "B25044_003E", "B25044_010E"]
    print("downloading ACS block groups …")
    bg = get(age + veh, "block group:*", "state:55 county:025 tract:*")
    bg["bg"] = bg["state"] + bg["county"] + bg["tract"] + bg["block group"]
    bg["age65_share"] = bg[age[1:]].sum(1) / bg["B01001_001E"].where(bg["B01001_001E"] > 0)
    bg["zero_vehicle_share"] = (bg["B25044_003E"] + bg["B25044_010E"]) / bg["B25044_001E"].where(bg["B25044_001E"] > 0)
    dis = ["B18101_001E"] + [f"B18101_{i:03d}E" for i in (4, 7, 10, 13, 16, 19, 23, 26, 29, 32, 35, 38)]
    print("downloading ACS tracts (disability) …")
    tr = get(dis, "tract:*", "state:55 county:025")
    tr["tract"] = tr["state"] + tr["county"] + tr["tract"]
    tr["disability_share"] = tr[dis[1:]].sum(1) / tr["B18101_001E"].where(tr["B18101_001E"] > 0)
    bg = bg[["bg", "age65_share", "zero_vehicle_share"]]
    tr = tr[["tract", "disability_share"]]
    bg.to_parquet(path_bg)
    tr.to_parquet(path_tr)
    return bg, tr


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
    area_km2 = blocks.to_crs(32616).area / 1e6
    blocks["pop_day"] = lodes_day_population(blocks["block_id"], blocks["pop_night"], area_km2)
    blocks["pop_gameday"] = blocks["pop_day"]
    used = ["LODES daytime population"]

    key = census_key()
    if key:
        bg, tr = acs_shares(key)
        b = blocks["block_id"].str[:12].map(bg.set_index("bg")["zero_vehicle_share"])
        a = blocks["block_id"].str[:12].map(bg.set_index("bg")["age65_share"])
        dsh = blocks["block_id"].str[:11].map(tr.set_index("tract")["disability_share"])
        blocks["zero_vehicle_share"] = b.fillna(b.median()).fillna(PLACEHOLDER_ZERO_VEHICLE).clip(0, 1)
        blocks["age65_share"] = a.fillna(a.median()).fillna(PLACEHOLDER_AGE65).clip(0, 1)
        blocks["disability_share"] = dsh.fillna(dsh.median()).fillna(PLACEHOLDER_DISABILITY).clip(0, 1)
        used.append("ACS shares")
    else:
        print("no CENSUS_API_KEY — ACS shares stay PLACEHOLDERS")

    d = blocks.geometry.representative_point().distance(shapely.Point(*CAMP_RANDALL))
    near = d.nsmallest(5).index
    blocks.loc[near, "pop_gameday"] = blocks.loc[near, "pop_day"] + GAMEDAY_CROWD / len(near)
    blocks.to_parquet(out / "blocks.parquet", index=False)

    # ---- facilities: nursing homes from CMS (certified, real resident counts); hospitals from OSM
    rows = []
    cms = cms_nursing_homes()
    for r in cms.itertuples():
        rows.append({"facility_id": f"cms_{r.ccn}", "type": "nursing_home", "name": str(r.name).title(),
                     "node_id": 0, "residents": float(r.residents), "lon": float(r.lon), "lat": float(r.lat)})
    used.append(f"CMS nursing homes ({len(cms)} in area)")
    hosp = cached_features("hospital", {"amenity": "hospital"})
    for i, r in hosp.iterrows():
        p = r.geometry.representative_point()
        rows.append({"facility_id": f"hospital_{i}", "type": "hospital", "name": r.get("name") or "hospital",
                     "node_id": 0, "residents": float(PLACEHOLDER_HOSPITAL_RESIDENTS), "lon": p.x, "lat": p.y})
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
    print("REAL:", ", ".join(used))
    todo = (["ACS shares"] if not key else []) + ["hospital occupancy", "depots", "ERG table"]
    print("PLACEHOLDERS still in use:", ", ".join(todo))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO / "data" / "silver"))
