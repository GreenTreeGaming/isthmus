from __future__ import annotations

import json
import types

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.assumptions_view import describe, json_safe
from backend.convert import Lookup, blocks_geojson, result_to_response
from contracts.engine_api import (BlockResult, BusRoute, EdgeLoad, ScenarioParams, ScenarioResult,
                                  Summary)

CONTRACT = json.loads(config.CONTRACT_RESPONSE.read_text())
BODY = {"release_lon": -89.3705, "release_lat": 43.079, "wind_from_deg": 225, "chemical": "chlorine"}
BLOCK_PROPS = set(CONTRACT["blocks"]["features"][0]["properties"]) - {"block_id"}


def _keys(got: dict, want: dict) -> None:
    for k, v in want.items():
        if k.startswith("_") or k == "blocks":
            continue
        assert k in got, k
        if isinstance(v, dict) and k != "edge_load":
            _keys(got[k], v)


def _same_shape(got: dict, want: dict) -> None:
    """Every contract key is present. Blocks are compacted: {block_id: properties}, geometry via GET /blocks."""
    _keys(got, want)
    assert isinstance(got["blocks"], dict)
    for props in got["blocks"].values():
        assert set(props) >= BLOCK_PROPS
    if got["edges"]["features"]:
        assert set(got["edges"]["features"][0]["properties"]) >= set(want["edges"]["features"][0]["properties"])
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
    assert "sim_clearance_s" in r.json()["summary"]


def test_blocks_match_simulate(client):
    geo = client.get("/blocks").json()
    ids = {f["properties"]["block_id"] for f in geo["features"]}
    assert ids and all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in geo["features"])
    assert set(client.post("/simulate", json=BODY).json()["blocks"]) <= ids


def test_simulate_validates(client):
    assert client.post("/simulate", json={**BODY, "chemical": "sarin"}).status_code == 422
    assert client.post("/simulate", json={**BODY, "compliance": 1.5}).status_code == 422


def test_rail_insights_assumptions(client):
    a = client.get("/assumptions")
    assert a.status_code == 200 and a.json()["groups"]
    rail = client.get("/rail").json()
    assert rail["type"] == "FeatureCollection" and rail["features"]
    ins = client.get("/insights").json()
    assert {"top_bottlenecks", "facilities_in_zone", "worst_wind"} <= set(ins)
    assert isinstance(client.get("/block-frequency").json(), list)


def test_gold_files_served(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOLD_DIR", tmp_path)
    (tmp_path / "insights.json").write_text(json.dumps({"source": "gold", "top_bottlenecks": [], "facilities_in_zone": [],
                                                        "worst_wind": [], "n_failed": 2}))
    (tmp_path / "block_frequency.json").write_text(json.dumps([{"block_id": "b1", "share_shelter": 0.4, "share_evacuate": 0.1}]))
    assert client.get("/insights").json()["n_failed"] == 2
    r = client.get("/block-frequency")
    assert r.headers["x-isthmus-source"] == "gold" and r.json()[0]["share_shelter"] == 0.4


def test_cors(client):
    r = client.options("/simulate", headers={"Origin": "http://localhost:5173",
                                             "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_assumptions_tuple_keys():
    """ERG_FALLBACK-style dicts with tuple keys must serialize (was a 500 with the real engine)."""
    mod = types.ModuleType("fake_assumptions")
    mod.ERG_FALLBACK = {("chlorine", "large", "day"): (500, 3000)}
    mod.CLASSES = frozenset({"b", "a"})
    mod.SIM_STEP_S = 30
    groups = describe(mod)
    json.dumps(groups)
    assert json_safe({("a", "b"): (1, 2)}) == {"a / b": [1, 2]}
    items = {i["key"]: i for g in groups for i in g["items"]}
    assert items["SIM_STEP_S"]["unit"] == "s" and "chlorine / large / day" in items["ERG_FALLBACK"]["value"]


def test_real_engine_assumptions_serialize():
    pytest.importorskip("engine")
    from engine import assumptions as a
    groups = describe(a)
    json.dumps(groups)
    keys = {i["key"] for g in groups for i in g["items"]}
    assert {"ERG_FALLBACK", "LANE_CAPACITY_VPH", "SIM_STEP_S"} <= keys


def test_mock_reacts_to_wind():
    from backend.mock import run_mock
    a = run_mock(ScenarioParams(release_lon=-89.3705, release_lat=43.079, wind_from_deg=225))
    b = run_mock(ScenarioParams(release_lon=-89.3705, release_lat=43.079, wind_from_deg=45))
    ids = lambda r: {k for k, p in r["blocks"].items() if p["decision"] != "outside"}
    assert ids(a) and ids(b) and ids(a) != ids(b)
    assert a["summary"]["sim_clearance_s"] >= a["summary"]["clearance_time_s"]


def test_converter_matches_contract():
    p = ScenarioParams(release_lon=-89.3705, release_lat=43.079)
    res = ScenarioResult(
        params=p,
        isolation_zone_wkt="POLYGON((-89.374 43.077,-89.367 43.077,-89.367 43.081,-89.374 43.077))",
        protect_zone_wkt="POLYGON((-89.371 43.079,-89.35 43.09,-89.345 43.083,-89.371 43.079))",
        blocks=[BlockResult("b1", "evacuate", 1500.0, 1100.0, 0, 140.0, 35.0, 8.0),
                BlockResult("missing", "shelter", None, None, None, 0, 0, 0)],
        edges=[EdgeLoad(101, 2900.0, 1.35, 840.0, True)],
        buses=[BusRoute(0, ["garage_main", "stop_1", "shelter_east"], [0.0, 600.0, 900.0], [0, 5, 0], [1, 2, 99],
                        deadline_s=[None, 840.0, None])],
        summary=Summary(7380, 18240, 3150, 940, 60, [101], 2140, sim_clearance_s=9900),
        load_timeline={101: [0.1, 0.5, 1.35]},
    )
    lk = Lookup(
        block_geom={"b1": {"type": "Polygon", "coordinates": (((0.1234567, 0.0), (1, 0), (1, 1), (0.1234567, 0.0)),)}},
        block_vuln={"b1": 0.4},
        edge_geom={101: [[-89.378, 43.068], [-89.372, 43.062]]},
        edge_name={101: "John Nolen Dr"},
        node_coord={1: [-89.35, 43.09], 2: [-89.33, 43.1]},
    )
    out = result_to_response(res, lk, step_s=30)
    _same_shape(out, CONTRACT)
    assert out["summary"]["sim_clearance_s"] == 9900
    assert [f["properties"]["kind"] for f in out["zones"]["features"]] == ["isolation", "protect"]
    assert list(out["blocks"]) == ["b1"]                 # unknown block skipped, not crashed
    assert out["blocks"]["b1"]["vulnerability"] == 0.4
    assert out["buses"][0]["path"] == [[-89.35, 43.09], [-89.33, 43.1]]  # unknown node dropped
    assert out["buses"][0]["deadline_s"] == [None, 840.0, None]  # same order as stops
    assert out["timeline"] == {"step_s": 30, "edge_load": {"101": [0.1, 0.5, 1.35]}}
    geo = blocks_geojson(lk)
    assert geo["features"][0]["properties"] == {"block_id": "b1"}
    assert geo["features"][0]["geometry"]["coordinates"][0][0] == [0.123457, 0.0]


def test_converter_deadlines_missing_or_mismatched():
    from backend.convert import _deadlines
    assert _deadlines(BusRoute(0, ["g", "s"], [0.0, 1.0], [0, 0], [])) == [None, None]
    assert _deadlines(BusRoute(0, ["g", "p", "s"], [0.0, 1.0, 2.0], [0, 1, 0], [], deadline_s=[None, 5.0])) == [None] * 3


def test_mock_bus_deadlines_respected():
    from backend.mock import run_mock
    for tod in ("day", "night"):
        r = run_mock(ScenarioParams(release_lon=-89.3705, release_lat=43.079, time_of_day=tod, bus_count=5))
        for b in r["buses"]:
            assert len(b["deadline_s"]) == len(b["stops"])
            assert b["deadline_s"][0] is None and b["deadline_s"][-1] is None
            for t, d in zip(b["arrival_s"], b["deadline_s"]):
                assert d is None or t <= d   # a scheduled stop is never late
