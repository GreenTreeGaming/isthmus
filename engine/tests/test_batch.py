import json

import pytest

from engine import assumptions as A
from engine.batch import RESULT_SCHEMA, gold_tables, release_points, run_partition, scenario_grid


@pytest.fixture(autouse=True)
def fast_buses(monkeypatch):
    monkeypatch.setattr(A, "BUS_SOLVER_TIME_LIMIT_S", 0.2)


def test_release_points_on_rail(net):
    pts = release_points(net, 5)
    assert len(pts) == 5 and len(set(pts)) == 5


def test_grid_size(net):
    g = scenario_grid(net, n_points=3, winds=(0, 90), times=("day", "night"))
    assert len(g) == 3 * 2 * 2
    assert g["scenario_id"].is_unique


def test_partition_matches_schema_and_gold_shape(net, synth_dir):
    g = scenario_grid(net, n_points=2, winds=(225, 45), wind_speeds=(1.0,), times=("day",), random_closures=1)
    res = run_partition(g, str(synth_dir))
    assert list(res.columns) == [c.split()[0] for c in RESULT_SCHEMA.split(", ")]
    assert res["error"].isna().all(), res["error"].dropna().tolist()
    gold = gold_tables(res, net)
    ins = gold["insights"]
    assert ins["n_scenarios"] == len(g)
    json.dumps(ins)
    # same shape as the frontend's Insights type
    for b in ins["top_bottlenecks"]:
        assert set(b) == {"edge_id", "name", "times_bottleneck", "share"}
    for f in ins["facilities_in_zone"]:
        assert set(f) == {"facility_id", "name", "type", "share"}
    for w in ins["worst_wind"]:
        assert {"wind_from_deg", "mean_clearance_s", "mean_unserved", "n"} <= set(w)
    assert len(gold["block_frequency"]) == len(net.blocks)


def test_bad_row_is_captured_not_raised(net, synth_dir):
    g = scenario_grid(net, n_points=1, winds=(0,), times=("day",))
    g.loc[0, "chemical"] = "unobtainium"
    res = run_partition(g, str(synth_dir))
    assert res.loc[0, "error"] and "KeyError" in res.loc[0, "error"]
