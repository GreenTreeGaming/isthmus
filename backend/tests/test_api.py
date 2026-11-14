from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.convert import Lookup, result_to_response
from contracts.engine_api import (BlockResult, BusRoute, EdgeLoad, ScenarioParams, ScenarioResult,
                                  Summary)

CONTRACT = json.loads(config.CONTRACT_RESPONSE.read_text())
BODY = {"release_lon": -89.3705, "release_lat": 43.079, "wind_from_deg": 225, "chemical": "chlorine"}


def _keys(got: dict, want: dict) -> None:
    for k, v in want.items():
        if k.startswith("_"):
            continue
        assert k in got, k
        if isinstance(v, dict) and k != "edge_load":
            _keys(got[k], v)


def _same_shape(got: dict, want: dict) -> None:
    """Every key in the contract example must be present in the response."""
    _keys(got, want)
    for fc in ("blocks", "edges"):
        if got[fc]["features"]:
            assert set(got[fc]["features"][0]["properties"]) >= set(want[fc]["features"][0]["properties"])
    if got["buses"]:
        assert set(got["buses"][0]) >= set(want["buses"][0])


@pytest.fixture(params=["placeholder", "mock"])
def client(request, monkeypatch):
    monkeypatch.setattr(config, "ENGINE_MODE", request.param)
    with TestClient(__import__("backend.main", fromlist=["app"]).app) as c:
        yield c


def test_simulate_shape(client):
    r = client.post("/simulate", json=BODY)
    assert r.status_code == 200
    _same_shape(r.json(), CONTRACT)
    assert r.json()["params"]["wind_from_deg"] == 225


def test_simulate_validates(client):
    assert client.post("/simulate", json={**BODY, "chemical": "sarin"}).status_code == 422
    assert client.post("/simulate", json={**BODY, "compliance": 1.5}).status_code == 422


def test_rail_and_insights(client):
    rail = client.get("/rail").json()
    assert rail["type"] == "FeatureCollection" and rail["features"]
    ins = client.get("/insights").json()
    assert {"top_bottlenecks", "facilities_in_zone", "worst_wind"} <= set(ins)


def test_cors(client):
    r = client.options("/simulate", headers={"Origin": "http://localhost:5173",
                                             "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_mock_reacts_to_wind():
    from backend.mock import run_mock
    a = run_mock(ScenarioParams(release_lon=-89.3705, release_lat=43.079, wind_from_deg=225))
    b = run_mock(ScenarioParams(release_lon=-89.3705, release_lat=43.079, wind_from_deg=45))
    ids = lambda r: {f["properties"]["block_id"] for f in r["blocks"]["features"]
                     if f["properties"]["decision"] != "outside"}
    assert ids(a) and ids(b) and ids(a) != ids(b)


def test_converter_matches_contract():
    p = ScenarioParams(release_lon=-89.3705, release_lat=43.079)
    res = ScenarioResult(
        params=p,
        isolation_zone_wkt="POLYGON((-89.374 43.077,-89.367 43.077,-89.367 43.081,-89.374 43.077))",
        protect_zone_wkt="POLYGON((-89.371 43.079,-89.35 43.09,-89.345 43.083,-89.371 43.079))",
        blocks=[BlockResult("b1", "evacuate", 1500.0, 1100.0, 0, 140.0, 35.0, 8.0),
                BlockResult("missing", "shelter", None, None, None, 0, 0, 0)],
        edges=[EdgeLoad(101, 2900.0, 1.35, 840.0, True)],
        buses=[BusRoute(0, ["garage_main", "shelter_east"], [0.0, 900.0], [0, 0], [1, 2, 99])],
        summary=Summary(7380, 18240, 3150, 940, 60, [101], 2140),
        load_timeline={101: [0.1, 0.5, 1.35]},
    )
    lk = Lookup(
        block_geom={"b1": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        block_vuln={"b1": 0.4},
        edge_geom={101: [[-89.378, 43.068], [-89.372, 43.062]]},
        edge_name={101: "John Nolen Dr"},
        node_coord={1: [-89.35, 43.09], 2: [-89.33, 43.1]},
    )
    out = result_to_response(res, lk, step_s=30)
    _same_shape(out, CONTRACT)
    assert [f["properties"]["kind"] for f in out["zones"]["features"]] == ["isolation", "protect"]
    assert len(out["blocks"]["features"]) == 1          # unknown block skipped, not crashed
    assert out["blocks"]["features"][0]["properties"]["vulnerability"] == 0.4
    assert out["buses"][0]["path"] == [[-89.35, 43.09], [-89.33, 43.1]]  # unknown node dropped
    assert out["timeline"] == {"step_s": 30, "edge_load": {"101": [0.1, 0.5, 1.35]}}
    assert out["params"]["closed_edge_ids"] == []
