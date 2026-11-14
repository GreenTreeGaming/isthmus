import numpy as np
import shapely

from engine.evacgraph import build_evac_graph
from engine.hazard import build_hazard
from engine.network import to_metric
from engine.synthetic import center_release


def _hz(net, wind_from=270.0, speed=4.0, size="large"):
    lon, lat = center_release()
    return build_hazard(net, lon, lat, "chlorine", size, "day", wind_from, speed)


def test_zone_points_downwind(net):
    hz = _hz(net, wind_from=270.0)        # wind FROM the west → gas goes east
    east = (hz.rx + 700, hz.ry)
    west = (hz.rx - 700, hz.ry)
    assert hz.in_zone(*east)
    assert not hz.in_zone(*west)


def test_wind_from_north_goes_south(net):
    hz = _hz(net, wind_from=0.0)
    assert hz.in_zone(hz.rx, hz.ry - 700)
    assert not hz.in_zone(hz.rx, hz.ry + 700)


def test_isolation_circle_all_around(net):
    hz = _hz(net)
    r = hz.isolation_m * 0.9
    for dx, dy in [(r, 0), (-r, 0), (0, r), (0, -r)]:
        assert hz.in_zone(hz.rx + dx, hz.ry + dy)


def test_arrival_increases_with_distance(net):
    hz = _hz(net, speed=4.0)
    t = hz.arrival_s([hz.rx + 200, hz.rx + 800], [hz.ry, hz.ry])
    assert t[0] < t[1]
    assert np.isclose(t[1], 800 / 4.0)
    assert np.isnan(hz.arrival_s(hz.rx - 2000, hz.ry))


def test_wkt_is_lonlat(net):
    iso, prot = _hz(net).wkt_lonlat()
    lon, lat = center_release()
    c = shapely.from_wkt(iso).centroid
    assert abs(c.x - lon) < 1e-3 and abs(c.y - lat) < 1e-3
    assert shapely.from_wkt(prot).contains(shapely.Point(lon + 0.01, lat))


def test_road_rules(net):
    hz = _hz(net)
    eg = build_evac_graph(net, hz)
    assert eg.exits, "need exits"
    nid = eg.node_ids
    for t, h in zip(eg.tails, eg.heads):
        u, v = nid[t], nid[h]
        zu = hz.in_zone(net.G.nodes[u]["x"], net.G.nodes[u]["y"])
        zv = hz.in_zone(net.G.nodes[v]["x"], net.G.nodes[v]["y"])
        assert not (zv and not zu), "no edge may enter the zone from outside"
        assert t not in eg.exits, "exits have no outgoing arcs"
    for e in eg.exits:
        n = nid[e]
        assert not hz.in_region(net.G.nodes[n]["x"], net.G.nodes[n]["y"])


def test_zone_edges_kept_not_deleted(net):
    hz = _hz(net)
    eg = build_evac_graph(net, hz)
    assert eg.in_zone[eg.tails].any(), "edges starting inside the zone must remain"
    assert not eg.unreachable


def test_closed_edges_removed(net):
    hz = _hz(net)
    eg = build_evac_graph(net, hz)
    victim = int(eg.edge_id[0])
    eg2 = build_evac_graph(net, hz, closed_edge_ids=(victim,))
    assert victim not in set(eg2.edge_id.tolist())


def test_contraflow_raises_outbound_capacity(net):
    hz = _hz(net)
    base = build_evac_graph(net, hz)
    cf = build_evac_graph(net, hz, contraflow=True)
    assert cf.cap_vph.max() > base.cap_vph.max()


def test_erg_table3_wind_bands():
    from engine import assumptions as A
    MI = A.MI
    # chlorine rail tank car, day: 6.0 / 3.9 / 3.2 mi at low / moderate / high wind
    assert A.erg_wind_factor("chlorine", "large", "day", 1.5) == 1.0
    assert abs(A.ERG_FALLBACK[("chlorine", "large", "day")][1] * A.erg_wind_factor("chlorine", "large", "day", 4.0) - 3.9 * MI) < 1e-6
    assert abs(A.ERG_FALLBACK[("chlorine", "large", "day")][1] * A.erg_wind_factor("chlorine", "large", "day", 8.0) - 3.2 * MI) < 1e-6
    assert A.erg_wind_factor("chlorine", "small", "day", 8.0) == 1.0     # Table 1 has no wind bands
    assert A.erg_wind_band(2.0) == 0 and A.erg_wind_band(4.0) == 1 and A.erg_wind_band(6.0) == 2


def test_stronger_wind_smaller_zone(net):
    lon, lat = center_release()
    calm = build_hazard(net, lon, lat, "chlorine", "large", "day", 270.0, 1.5)
    windy = build_hazard(net, lon, lat, "chlorine", "large", "day", 270.0, 6.0)
    assert windy.protect_m < calm.protect_m
