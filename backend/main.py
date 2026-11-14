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
    log.info("engine mode: %s", config.ENGINE_MODE)
    yield
    STATE.clear()


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


@app.get("/insights")
def insights(response: Response) -> dict[str, Any]:
    """Gold-table JSON from data/gold/*.json (merged by file stem); placeholder until it exists."""
    files = sorted(config.GOLD_DIR.glob("*.json")) if config.GOLD_DIR.exists() else []
    if not files:
        response.headers["X-Isthmus-Source"] = "placeholder"
        return _load_json(config.PLACEHOLDER_DIR / "insights.json")
    response.headers["X-Isthmus-Source"] = "gold"
    if len(files) == 1 and files[0].stem == "insights":
        return {**_load_json(files[0]), "source": "gold"}
    return {"source": "gold", **{f.stem: _load_json(f) for f in files}}


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
    items = [{"name": k, "value": v if isinstance(v, (int, float, str, bool)) else json.dumps(v, default=str)}
             for k, v in vars(a).items() if k.isupper()]
    response.headers["X-Isthmus-Source"] = "engine"
    return {**base, "source": "engine/assumptions.py", "groups": [{"title": "engine/assumptions.py", "items": items}]}
