"""Load silver tables (contracts/data_schema.md) into an in-memory Network and cache it as a pickle."""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from engine import assumptions as A

CACHE_NAME = "_network_cache.pkl"
CACHE_VERSION = 3

_TO_METRIC = Transformer.from_crs("EPSG:4326", A.METRIC_CRS, always_xy=True)
_TO_LONLAT = Transformer.from_crs(A.METRIC_CRS, "EPSG:4326", always_xy=True)


def to_metric(lon, lat):
    return _TO_METRIC.transform(lon, lat)


def to_lonlat(x, y):
    return _TO_LONLAT.transform(x, y)


@dataclass
class Network:
    """Road graph + population tables, all in one picklable object.

    G: DiGraph keyed by node_id. Node attrs: x, y (meters), lon, lat, is_exit.
       Edge attrs: edge_id, length_m, travel_time_s, capacity_vph, lanes, road_class, name.
    Tables are pandas DataFrames with metric x, y columns added.
    """

    G: nx.DiGraph
    blocks: pd.DataFrame
    facilities: pd.DataFrame
    pickups: pd.DataFrame
    depots: pd.DataFrame
    rails: list
    erg: dict[tuple[str, str, str], tuple[float, float]]
    edge_uv: dict[int, tuple[int, int]] = field(default_factory=dict)
    edge_coords: dict[int, list[list[float]]] = field(default_factory=dict)

    def node_xy(self, n: int) -> tuple[float, float]:
        d = self.G.nodes[n]
        return d["x"], d["y"]


# --------------------------------------------------------------------------- reading

def _geom(col: pd.Series) -> np.ndarray:
    vals = col.to_numpy()
    if len(vals) == 0:
        return vals
    first = next((v for v in vals if v is not None), None)
    if isinstance(first, (bytes, bytearray, memoryview)):
        return shapely.from_wkb(vals)
    if isinstance(first, str):
        return shapely.from_wkt(vals)
    return vals  # already shapely


def _read(data_dir: Path, name: str, required: bool = True) -> pd.DataFrame | None:
    path = data_dir / f"{name}.parquet"
    if not path.exists():
        if required:
            raise FileNotFoundError(f"missing silver table: {path}")
        return None
    df = pd.read_parquet(path)
    if "geometry" in df.columns:
        df["geometry"] = _geom(df["geometry"])
    return df


def _clean_class(rc) -> str:
    if rc is None or (isinstance(rc, float) and np.isnan(rc)):
        return "unclassified"
    if isinstance(rc, (list, tuple, np.ndarray)):
        rc = rc[0] if len(rc) else "unclassified"
    rc = str(rc).strip()
    if rc.startswith("["):
        rc = rc.strip("[]").split(",")[0].strip(" '\"")
    return rc or "unclassified"


def lane_capacity(road_class: str) -> float:
    if road_class.endswith("_link"):
        return A.LINK_CAPACITY_VPH
    return A.LANE_CAPACITY_VPH.get(road_class, A.DEFAULT_LANE_CAPACITY_VPH)


def _base(road_class: str) -> str:
    return road_class.removesuffix("_link")


def _fill_edges(edges: pd.DataFrame) -> pd.DataFrame:
    e = edges.copy()
    e["road_class"] = e["road_class"].map(_clean_class)
    base = e["road_class"].map(_base)
    speed = pd.to_numeric(e.get("speed_kph"), errors="coerce")
    e["speed_kph"] = speed.where(speed > 0, base.map(lambda c: A.DEFAULT_SPEED_KPH.get(c, A.DEFAULT_SPEED_FALLBACK_KPH)))
    lanes = pd.to_numeric(e.get("lanes"), errors="coerce")
    e["lanes"] = lanes.where(lanes > 0, base.map(lambda c: A.DEFAULT_LANES.get(c, A.DEFAULT_LANES_FALLBACK))).astype(int)
    cap = pd.to_numeric(e.get("capacity_vph"), errors="coerce")
    computed = e["lanes"] * e["road_class"].map(lane_capacity)
    e["capacity_vph"] = cap.where(cap > 0, computed)
    e["length_m"] = pd.to_numeric(e["length_m"], errors="coerce").fillna(1.0).clip(lower=1.0)
    e["travel_time_s"] = e["length_m"] / (e["speed_kph"] / 3.6)
    return e


def _with_xy(df: pd.DataFrame, G: nx.DiGraph) -> pd.DataFrame:
    """Add metric x, y: from lon/lat if present, else polygon centroid, else snapped node."""
    df = df.copy()
    if {"lon", "lat"} <= set(df.columns):
        x, y = to_metric(df["lon"].to_numpy(float), df["lat"].to_numpy(float))
    elif "geometry" in df.columns:
        c = shapely.centroid(df["geometry"].to_numpy())
        x, y = to_metric(shapely.get_x(c), shapely.get_y(c))
    else:
        x = np.array([G.nodes[n]["x"] for n in df["node_id"]])
        y = np.array([G.nodes[n]["y"] for n in df["node_id"]])
    df["x"], df["y"] = x, y
    return df


def _snap_missing(df: pd.DataFrame, G: nx.DiGraph) -> pd.DataFrame:
    """Drop rows whose node_id is not in the graph after snapping them to the nearest node."""
    if df.empty:
        return df
    ids = np.array(list(G.nodes))
    nx_ = np.array([G.nodes[n]["x"] for n in ids])
    ny_ = np.array([G.nodes[n]["y"] for n in ids])
    bad = ~df["node_id"].isin(G.nodes)
    if bad.any():
        for i in df.index[bad]:
            j = np.argmin((nx_ - df.at[i, "x"]) ** 2 + (ny_ - df.at[i, "y"]) ** 2)
            df.at[i, "node_id"] = int(ids[j])
    df["node_id"] = df["node_id"].astype("int64")
    return df


def build_network(data_dir: str | Path) -> Network:
    d = Path(data_dir)
    nodes = _read(d, "road_nodes")
    edges = _fill_edges(_read(d, "road_edges"))
    blocks = _read(d, "blocks")
    facilities = _read(d, "facilities", required=False)
    pickups = _read(d, "pickup_points", required=False)
    depots = _read(d, "depots", required=False)
    rails = _read(d, "rail_lines", required=False)
    erg_df = _read(d, "erg_distances", required=False)

    G = nx.DiGraph()
    x, y = to_metric(nodes["lon"].to_numpy(float), nodes["lat"].to_numpy(float))
    is_exit = nodes["is_exit"].fillna(False).astype(bool) if "is_exit" in nodes else pd.Series(False, index=nodes.index)
    for nid, lon, lat, xi, yi, ex in zip(nodes["node_id"], nodes["lon"], nodes["lat"], x, y, is_exit):
        G.add_node(int(nid), lon=float(lon), lat=float(lat), x=float(xi), y=float(yi), is_exit=bool(ex))

    edge_uv: dict[int, tuple[int, int]] = {}
    edge_coords: dict[int, list[list[float]]] = {}
    has_geom = "geometry" in edges.columns
    for row in edges.itertuples(index=False):
        u, v, eid = int(row.u), int(row.v), int(row.edge_id)
        if u == v or u not in G or v not in G:
            continue
        coords = None
        if has_geom and row.geometry is not None:
            coords = [list(c) for c in shapely.get_coordinates(row.geometry).tolist()]
        if coords is None:
            coords = [[G.nodes[u]["lon"], G.nodes[u]["lat"]], [G.nodes[v]["lon"], G.nodes[v]["lat"]]]
        if G.has_edge(u, v):
            # parallel OSM edges: merge into one (add capacity, keep the faster)
            ex = G.edges[u, v]
            ex["capacity_vph"] += float(row.capacity_vph)
            ex["lanes"] += int(row.lanes)
            if row.travel_time_s < ex["travel_time_s"]:
                ex["travel_time_s"] = float(row.travel_time_s)
                ex["length_m"] = float(row.length_m)
            edge_uv[eid] = (u, v)
            continue
        G.add_edge(
            u, v,
            edge_id=eid,
            length_m=float(row.length_m),
            travel_time_s=float(row.travel_time_s),
            capacity_vph=float(row.capacity_vph),
            lanes=int(row.lanes),
            road_class=str(row.road_class),
            name=None if pd.isna(getattr(row, "name", None)) else str(row.name),
        )
        edge_uv[eid] = (u, v)
        edge_coords[eid] = coords

    blocks = _snap_missing(_with_xy(blocks, G), G)
    for col in ("pop_night", "pop_day", "pop_gameday", "households",
                "zero_vehicle_share", "disability_share", "age65_share"):
        blocks[col] = pd.to_numeric(blocks.get(col), errors="coerce").fillna(0.0)
    blocks["block_id"] = blocks["block_id"].astype(str)

    def _opt(df, cols):
        if df is None or df.empty:
            return pd.DataFrame(columns=cols + ["x", "y"])
        return _snap_missing(_with_xy(df, G), G)

    facilities = _opt(facilities, ["facility_id", "type", "name", "node_id", "residents"])
    if not facilities.empty:
        facilities["residents"] = pd.to_numeric(facilities["residents"], errors="coerce").fillna(0.0)
        facilities["facility_id"] = facilities["facility_id"].astype(str)
    pickups = _opt(pickups, ["pickup_id", "kind", "node_id"])
    depots = _opt(depots, ["depot_id", "kind", "name", "node_id"])

    erg = dict(A.ERG_FALLBACK)
    if erg_df is not None:
        for r in erg_df.itertuples(index=False):
            erg[(str(r.chemical), str(r.spill_size), str(r.time_of_day))] = (float(r.isolation_m), float(r.protect_m))

    rail_geoms = [] if rails is None else [g for g in rails["geometry"] if g is not None]

    return Network(
        G=G, blocks=blocks.reset_index(drop=True), facilities=facilities.reset_index(drop=True),
        pickups=pickups.reset_index(drop=True), depots=depots.reset_index(drop=True),
        rails=rail_geoms, erg=erg, edge_uv=edge_uv, edge_coords=edge_coords,
    )


def load_network(data_dir: str | Path, use_cache: bool = True) -> Network:
    """Build the network from silver Parquet, reusing a pickle cache when the inputs haven't changed."""
    d = Path(data_dir)
    cache = d / CACHE_NAME
    newest = max((p.stat().st_mtime for p in d.glob("*.parquet")), default=0.0)
    if use_cache and cache.exists() and cache.stat().st_mtime >= newest:
        try:
            with cache.open("rb") as f:
                version, net = pickle.load(f)
            if version == CACHE_VERSION:
                return net
        except Exception:
            pass
    net = build_network(d)
    if use_cache:
        try:
            with cache.open("wb") as f:
                pickle.dump((CACHE_VERSION, net), f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass  # read-only location (e.g. a shared Volume) — fine, just slower
    return net
