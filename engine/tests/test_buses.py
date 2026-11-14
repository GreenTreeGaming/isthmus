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
