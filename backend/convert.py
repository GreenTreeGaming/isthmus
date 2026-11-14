"""ScenarioResult (contracts/engine_api.py) -> api_response.json shape (contracts/api_response.json).

ScenarioResult carries ids, not geometry, so we join against the silver tables
(blocks, road_edges, road_nodes) loaded once at startup into a `Lookup`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely import wkt
from shapely.geometry import mapping

from backend.schemas import params_to_json
from contracts.engine_api import ScenarioResult

DEFAULT_STEP_S = 30


@dataclass
class Lookup:
    block_geom: dict[str, dict[str, Any]] = field(default_factory=dict)   # block_id -> GeoJSON geometry
    block_vuln: dict[str, float] = field(default_factory=dict)            # block_id -> 0..1
    edge_geom: dict[int, list[list[float]]] = field(default_factory=dict)  # edge_id -> [[lon, lat], ...]
    edge_name: dict[int, str | None] = field(default_factory=dict)
    node_coord: dict[int, list[float]] = field(default_factory=dict)      # node_id -> [lon, lat]


def vulnerability_index(zero_vehicle: float, disability: float, age65: float) -> float:
    """Share-based index (0..1) of residents likely to need help. Area-level, never individual."""
    vals = [0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)
            for v in (zero_vehicle, disability, age65)]
    return max(0.0, min(1.0, 0.45 * vals[0] + 0.35 * vals[1] + 0.20 * vals[2]))


def load_lookup(data_dir: Path) -> Lookup:
    """Read silver (or fixture) tables. Imported lazily so placeholder mode doesn't need geopandas."""
    import geopandas as gpd
    import pandas as pd

    lk = Lookup()
    blocks = gpd.read_parquet(data_dir / "blocks.parquet")
    raw = [vulnerability_index(z, d, a) for z, d, a in
           zip(blocks["zero_vehicle_share"], blocks["disability_share"], blocks["age65_share"])]
    top = max(raw) if raw and max(raw) > 0 else 1.0
    for bid, geom, v in zip(blocks["block_id"], blocks.geometry, raw):
        lk.block_geom[str(bid)] = mapping(geom)
        lk.block_vuln[str(bid)] = round(v / top, 3)

    edges = gpd.read_parquet(data_dir / "road_edges.parquet")
    for eid, name, geom in zip(edges["edge_id"], edges["name"], edges.geometry):
        lk.edge_geom[int(eid)] = [list(c[:2]) for c in geom.coords]
        lk.edge_name[int(eid)] = None if pd.isna(name) else str(name)

    nodes = pd.read_parquet(data_dir / "road_nodes.parquet", columns=["node_id", "lon", "lat"])
    lk.node_coord = {int(n): [float(x), float(y)] for n, x, y in zip(nodes["node_id"], nodes["lon"], nodes["lat"])}
    return lk


def _num(x: float | None, nd: int = 1) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def _sim_step_s() -> int:
    try:
        from engine import assumptions  # type: ignore[import-not-found]
        return int(getattr(assumptions, "SIM_STEP_S", DEFAULT_STEP_S))
    except ImportError:
        return DEFAULT_STEP_S


def result_to_response(result: ScenarioResult, lk: Lookup, step_s: int | None = None) -> dict[str, Any]:
    zones = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"kind": kind}, "geometry": mapping(wkt.loads(text))}
        for kind, text in (("isolation", result.isolation_zone_wkt), ("protect", result.protect_zone_wkt))
        if text
    ]}

    block_features = []
    for b in result.blocks:
        geom = lk.block_geom.get(b.block_id)
        if geom is None:
            continue
        block_features.append({"type": "Feature", "geometry": geom, "properties": {
            "block_id": b.block_id,
            "decision": b.decision,
            "plume_arrival_s": _num(b.plume_arrival_s),
            "est_exit_time_s": _num(b.est_exit_time_s),
            "wave": b.wave,
            "drivers": _num(b.drivers),
            "walkers": _num(b.walkers),
            "need_bus": _num(b.need_bus),
            "vulnerability": lk.block_vuln.get(b.block_id, 0.0),
        }})

    edge_features = []
    for e in result.edges:
        coords = lk.edge_geom.get(e.edge_id)
        if not coords:
            continue
        edge_features.append({"type": "Feature",
                              "geometry": {"type": "LineString", "coordinates": coords},
                              "properties": {
                                  "edge_id": e.edge_id,
                                  "name": lk.edge_name.get(e.edge_id),
                                  "flow_veh": _num(e.flow_veh, 0),
                                  "peak_load_ratio": _num(e.peak_load_ratio, 3),
                                  "congested_at_s": _num(e.congested_at_s),
                                  "is_bottleneck": bool(e.is_bottleneck),
                              }})

    buses = [{
        "bus_id": r.bus_id,
        "stops": list(r.stops),
        "arrival_s": [_num(t) for t in r.arrival_s],
        "load": [int(x) for x in r.load],
        "path": [lk.node_coord[n] for n in r.path_node_ids if n in lk.node_coord],
    } for r in result.buses]

    s = result.summary
    return {
        "params": params_to_json(result.params),
        "summary": {
            "clearance_time_s": _num(s.clearance_time_s),
            "people_evacuating": _num(s.people_evacuating, 0),
            "people_sheltering": _num(s.people_sheltering, 0),
            "need_bus_total": _num(s.need_bus_total, 0),
            "need_bus_unserved": _num(s.need_bus_unserved, 0),
            "bottleneck_edge_ids": list(s.bottleneck_edge_ids),
            "runtime_ms": _num(s.runtime_ms, 0),
        },
        "zones": zones,
        "blocks": {"type": "FeatureCollection", "features": block_features},
        "edges": {"type": "FeatureCollection", "features": edge_features},
        "buses": buses,
        "timeline": {
            "step_s": step_s if step_s is not None else _sim_step_s(),
            "edge_load": {str(k): [round(float(v), 3) for v in vals] for k, vals in result.load_timeline.items()},
        },
    }
