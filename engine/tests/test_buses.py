import networkx as nx

from engine import assumptions as A
from engine.buses import Stop, plan_buses


def _line():
    # garage 0 — 1 — 2 — 3 shelter, 100 s per hop, both directions
    G = nx.DiGraph()
    eid = 1
    for a, b in [(0, 1), (1, 2), (2, 3)]:
        for u, v in [(a, b), (b, a)]:
            G.add_edge(u, v, edge_id=eid, travel_time_s=100.0)
            eid += 1
    return G


def _plan(stops, buses=2, cap=60, **kw):
    return plan_buses(_line(), {}, set(), set(), ("garage", 0), ("shelter", 3), stops, buses, cap,
                      dispatch_s=0, **kw)


def test_reachable_stop_served():
    p = _plan([Stop("s1", 1, 20, deadline_s=5000)])
    assert p.served == 20 and p.unserved == 0
    r = p.routes[0]
    assert r.stops == ["garage", "s1", "shelter"]
    assert r.load == [0, 20, 0]
    assert r.arrival_s[1] == 100
    assert r.path_node_ids[0] == 0 and r.path_node_ids[-1] == 3


def test_deadline_too_early_is_unserved():
    p = _plan([Stop("late", 2, 10, deadline_s=50)])
    assert p.served == 0 and p.unserved == 10


def test_big_stop_split_across_buses():
    p = _plan([Stop("nh", 2, 130, deadline_s=10_000, board_s_per_person=A.NURSING_BOARDING_S_PER_PERSON)],
              buses=3, cap=60)
    assert p.served == 130
    assert all(max(r.load) <= 60 for r in p.routes)


def test_not_enough_buses():
    p = _plan([Stop("nh", 2, 130, deadline_s=10_000)], buses=1, cap=60)
    assert p.served == 60 and p.unserved == 70


def test_congested_times_used():
    slow = {e: 1000.0 for e in range(1, 7)}
    p = plan_buses(_line(), slow, set(), set(), ("garage", 0), ("shelter", 3),
                   [Stop("s", 1, 5, deadline_s=500)], 1, 60, dispatch_s=0)
    assert p.unserved == 5          # 1000 s to reach node 1 > 500 s deadline


def test_deadlines_reported_and_respected():
    p = _plan([Stop("a", 1, 5, deadline_s=5000), Stop("b", 2, 5, deadline_s=6000)])
    for r in p.routes:
        assert len(r.deadline_s) == len(r.stops)
        assert r.deadline_s[0] is None and r.deadline_s[-1] is None
        for t, d in zip(r.arrival_s[1:-1], r.deadline_s[1:-1]):
            assert t <= d


def test_scipy_and_networkx_paths_agree(net):
    """Fast (scipy) and fallback (networkx) shortest paths must give identical times and paths."""
    from engine.buses import _paths_between, _paths_between_nx
    G = net.G
    keys = list(G.nodes)[::9][:12]
    zone = {d["edge_id"] for _, _, d in list(G.edges(data=True))[::3]}

    def time(u, v, d):
        return d["travel_time_s"]

    def cost(u, v, d):
        return d["travel_time_s"] * (3 if d["edge_id"] in zone else 1)

    def along(path, f):
        return sum(f(a, b, G.edges[a, b]) for a, b in zip(path, path[1:]))

    m1, p1 = _paths_between(G, keys, cost, time)
    m2, p2 = _paths_between_nx(G, keys, cost, time)
    for i in range(len(keys)):
        for j in range(len(keys)):
            a, b = p1.get((i, j)), p2.get((i, j))
            assert a[0] == keys[i] and a[-1] == keys[j]
            # both are lowest-cost routes (ties on a grid may pick different ones) ...
            assert abs(along(a, cost) - along(b, cost)) < 1e-6
            # ... and each reported time is the true time along the route it returned
            assert abs(m1[i][j] - along(a, time)) < 1e-6
            assert abs(m2[i][j] - along(b, time)) < 1e-6
