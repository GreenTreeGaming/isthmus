from engine import assumptions as A
from engine.network import CACHE_NAME, load_network
from engine.synthetic import NX, NY


def test_assumptions_sane():
    assert A.LANE_CAPACITY_VPH["motorway"] == 1800
    assert A.LANE_CAPACITY_VPH["secondary"] == 800
    assert 0 < A.WALK_SPEED_65_MPS < A.WALK_SPEED_MPS
    assert all(iso < prot for iso, prot in A.ERG_FALLBACK.values())


def test_graph_shape(net):
    assert net.G.number_of_nodes() == NX * NY
    expected_undirected = NY * (NX - 1) + NX * (NY - 1)
    assert net.G.number_of_edges() == 2 * expected_undirected


def test_missing_values_filled(net):
    for _, _, d in net.G.edges(data=True):
        assert d["capacity_vph"] > 0
        assert d["lanes"] >= 1
        assert d["travel_time_s"] > 0


def test_capacity_from_class(net):
    caps = {d["road_class"]: d["capacity_vph"] / d["lanes"] for _, _, d in net.G.edges(data=True)}
    assert caps["primary"] == A.LANE_CAPACITY_VPH["primary"]
    assert caps["residential"] == A.LANE_CAPACITY_VPH["residential"]


def test_tables_have_metric_xy(net):
    for df in (net.blocks, net.facilities, net.pickups, net.depots):
        assert {"x", "y", "node_id"} <= set(df.columns)
        assert df["node_id"].isin(net.G.nodes).all()
    assert len(net.rails) == 1
    assert ("chlorine", "large", "day") in net.erg


def test_cache_roundtrip(synth_dir, net):
    assert (synth_dir / CACHE_NAME).exists()
    again = load_network(synth_dir)
    assert again.G.number_of_edges() == net.G.number_of_edges()
