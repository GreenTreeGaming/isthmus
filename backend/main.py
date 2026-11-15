"""Isthmus API. Run from the repo root:  uvicorn backend.main:app --reload --port 8000"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.schemas import ScenarioParamsIn, params_to_json

log = logging.getLogger("isthmus")

STATE: dict[str, Any] = {}


def _load_json(path) -> Any:
    with open(path) as f:
        return json.load(f)


@asynccontextmanager
async def lifespan(_: FastAPI):
    STATE["mode"] = config.ENGINE_MODE
    if config.ENGINE_MODE == "real":
        # Load the engine network and the silver lookup ONCE; every request reuses them.
        import engine  # type: ignore[import-not-found]
        from backend.convert import load_lookup

        data_dir = config.silver_dir()
        STATE["network"] = engine.load_network(str(data_dir))
        STATE["lookup"] = load_lookup(data_dir)
        STATE["run_scenario"] = engine.run_scenario
        log.info("engine network loaded from %s", data_dir)
    elif config.ENGINE_MODE == "placeholder":
        STATE["placeholder"] = _load_json(config.CONTRACT_RESPONSE)
    STATE["blocks_geo"] = _static_blocks(config.ENGINE_MODE)
    log.info("engine mode: %s", config.ENGINE_MODE)
    yield
    STATE.clear()


def _static_blocks(mode: str) -> dict[str, Any]:
    if mode == "real":
        from backend.convert import blocks_geojson
        return blocks_geojson(STATE["lookup"])
    if mode == "mock":
        from backend.mock import blocks_geojson
        return blocks_geojson()
    fc = STATE["placeholder"]["blocks"]
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"block_id": f["properties"]["block_id"]}, "geometry": f["geometry"]}
        for f in fc["features"]]}


def compact_blocks(fc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """FeatureCollection of blocks -> {block_id: properties without geometry}."""
    out = {}
    for f in fc["features"]:
        props = dict(f["properties"])
        out[str(props.pop("block_id"))] = props
    return out


app = FastAPI(title="Isthmus API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Isthmus-Source"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_mode": STATE.get("mode", config.ENGINE_MODE)}


@app.post("/simulate")
def simulate(body: ScenarioParamsIn, response: Response) -> dict[str, Any]:
    params = body.to_engine()
    mode = STATE.get("mode", config.ENGINE_MODE)
    response.headers["X-Isthmus-Source"] = mode
    if mode == "placeholder":
        out = dict(STATE["placeholder"])
        out.pop("_comment", None)
        out["params"] = params_to_json(params)
        out["blocks"] = compact_blocks(out["blocks"])
        return out
    if mode == "mock":
        from backend.mock import run_mock
        return run_mock(params)

    from backend.convert import result_to_response
    try:
        result = STATE["run_scenario"](params, STATE["network"])
    except Exception as exc:  # surface engine failures to the UI instead of a bare 500
        log.exception("engine failed")
        raise HTTPException(status_code=500, detail=f"engine error: {exc}") from exc
    return result_to_response(result, STATE["lookup"])


@app.get("/blocks")
def blocks(response: Response) -> dict[str, Any]:
    """Static block outlines (fetch once). /simulate returns per-run block properties keyed by block_id."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["X-Isthmus-Source"] = STATE.get("mode", config.ENGINE_MODE)
    return STATE["blocks_geo"]


@app.get("/insights")
def insights(response: Response) -> dict[str, Any]:
    """data/gold/insights.json (written by engine/batch.py); placeholder until it exists."""
    path = config.GOLD_DIR / "insights.json"
    if not path.exists():
        response.headers["X-Isthmus-Source"] = "placeholder"
        return _load_json(config.PLACEHOLDER_DIR / "insights.json")
    response.headers["X-Isthmus-Source"] = "gold"
    return _load_json(path)


@app.get("/robustness")
def robustness(response: Response) -> dict[str, Any]:
    """data/gold/robustness.json (engine/robustness.py): the batch re-run under assumption variants; {} until it exists."""
    path = config.GOLD_DIR / "robustness.json"
    if not path.exists():
        response.headers["X-Isthmus-Source"] = "placeholder"
        return {}
    response.headers["X-Isthmus-Source"] = "gold"
    return _load_json(path)


@app.get("/block-frequency")
def block_frequency(response: Response) -> list[dict[str, Any]]:
    """data/gold/block_frequency.json: [{block_id, share_shelter, share_evacuate}]; empty until batch runs."""
    path = config.GOLD_DIR / "block_frequency.json"
    if not path.exists():
        response.headers["X-Isthmus-Source"] = "placeholder"
        return []
    response.headers["X-Isthmus-Source"] = "gold"
    return _load_json(path)


@app.get("/rail")
def rail(response: Response) -> dict[str, Any]:
    path = config.silver_dir() / "rail_lines.parquet"
    if path.exists():
        import geopandas as gpd

        response.headers["X-Isthmus-Source"] = str(path.parent.name)
        return json.loads(gpd.read_parquet(path).to_crs(4326).to_json())
    response.headers["X-Isthmus-Source"] = "placeholder"
    return _load_json(config.PLACEHOLDER_DIR / "rail.geojson")


@app.get("/assumptions")
def assumptions(response: Response) -> dict[str, Any]:
    """Engine assumptions (engine/assumptions.py is the single source of truth); placeholder until it exists."""
    base = _load_json(config.PLACEHOLDER_DIR / "assumptions.json")
    base.pop("_comment", None)
    try:
        from engine import assumptions as a  # type: ignore[import-not-found]
    except ImportError:
        response.headers["X-Isthmus-Source"] = "placeholder"
        return base
    from backend.assumptions_view import describe

    response.headers["X-Isthmus-Source"] = "engine"
    return {**base, "source": "engine/assumptions.py", "groups": describe(a)}
