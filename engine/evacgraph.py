"""The directed graph evacuees drive on for one scenario.

Rules (step 4 of the plan):
- Edges inside the zone are kept — people inside must drive out through them.
- Inside the zone, only edges moving away from the release are allowed (cost × HAZARD_COST_MULT).
  If some origin has no away-only path, toward edges are added back at a heavy penalty.
- Edges entering the zone from outside are blocked.
- Exit nodes: nodes outside the buffered region that border it (where roads leave the danger area).
- Closed edges are removed; contraflow turns all lanes of major roads outbound.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from engine import assumptions as A
from engine.hazard import Hazard
from engine.network import Network

SINK_EDGE = -1


@dataclass
class EvacGraph:
    node_ids: list[int]                    # index -> node_id
    index: dict[int, int]                  # node_id -> index
    tails: np.ndarray                      # arc arrays (road arcs only)
    heads: np.ndarray
    cap_vph: np.ndarray
    cost_s: np.ndarray                     # routing cost (penalized)
    tt_s: np.ndarray                       # free-flow travel time
    edge_id: np.ndarray
    exits: list[int]                       # node indices
    in_zone: np.ndarray                    # per node index
    relaxed: bool = False                  # toward-edges had to be added back
    unreachable: set[int] = field(default_factory=set)   # node_ids with no way out

    @property
    def n(self) -> int:
        return len(self.node_ids)

    def ff_time_to_exit(self) -> np.ndarray:
        """Free-flow seconds from every node to the nearest exit (inf if none). Reverse Dijkstra."""
        import heapq
        rev: list[list[tuple[int, float]]] = [[] for _ in range(self.n)]
        for a in range(len(self.tails)):
            rev[self.heads[a]].append((self.tails[a], self.tt_s[a]))
        dist = np.full(self.n, np.inf)
        pq = []
        for e in self.exits:
            dist[e] = 0.0
            pq.append((0.0, e))
        heapq.heapify(pq)
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for w, t in rev[u]:
                nd = d + t
                if nd < dist[w]:
                    dist[w] = nd
                    heapq.heappush(pq, (nd, w))
        return dist


def _reaches_exit(n: int, tails, heads, exits) -> np.ndarray:
    rev: list[list[int]] = [[] for _ in range(n)]
    for t, h in zip(tails, heads):
        rev[h].append(t)
    seen = np.zeros(n, bool)
    q = deque(exits)
    for e in exits:
        seen[e] = True
    while q:
        u = q.popleft()
        for w in rev[u]:
            if not seen[w]:
                seen[w] = True
                q.append(w)
    return seen


def build_evac_graph(net: Network, hz: Hazard, closed_edge_ids=(), contraflow: bool = False) -> EvacGraph:
    G = net.G
    closed = set(closed_edge_ids)
    all_nodes = np.array(list(G.nodes))
    xs = np.array([G.nodes[n]["x"] for n in all_nodes])
    ys = np.array([G.nodes[n]["y"] for n in all_nodes])
    in_region = dict(zip(all_nodes.tolist(), hz.in_region(xs, ys).tolist()))
    in_zone = dict(zip(all_nodes.tolist(), hz.in_zone(xs, ys).tolist()))
    dist = dict(zip(all_nodes.tolist(), hz.distance(xs, ys).tolist()))

    # Exits: outside the buffered region, adjacent to a region node.
    exits = {v for u, v in G.edges if in_region[u] and not in_region[v]}
    if not exits:
        # Zone swallows the whole study area: use the network boundary, farthest-from-release first.
        exits = {n for n in G.nodes if G.nodes[n].get("is_exit")}
    if not exits:
        far = sorted(G.nodes, key=lambda n: -dist[n])
        exits = set(far[: max(1, len(far) // 20)])

    keep = {n for n in G.nodes if in_region[n]} | exits
    node_ids = sorted(keep)
    index = {n: i for i, n in enumerate(node_ids)}

    # Contraflow: on major two-way roads inside the region, outbound direction takes both directions' capacity.
    cap_override: dict[tuple[int, int], float] = {}
    if contraflow:
        for u, v, d in G.edges(data=True):
            if u in keep and v in keep and d["road_class"] in A.CONTRAFLOW_CLASSES and G.has_edge(v, u):
                if dist[v] > dist[u]:
                    cap_override[(u, v)] = d["capacity_vph"] + G.edges[v, u]["capacity_vph"]
                    cap_override[(v, u)] = 0.0

    away, toward = [], []
    for u, v, d in G.edges(data=True):
        if u not in keep or v not in keep or u in exits:
            continue                          # once at an exit you're out
        if d["edge_id"] in closed:
            continue
        cap = cap_override.get((u, v), d["capacity_vph"])
        if cap <= 0:
            continue
        if in_zone[v] and not in_zone[u]:
            continue                          # never drive into the zone
        tt = d["travel_time_s"]
        arc = (index[u], index[v], cap, tt, d["edge_id"])
        if in_zone[u] or in_zone[v]:
            if dist[v] >= dist[u] - A.AWAY_TOLERANCE_M:
                away.append(arc + (tt * A.HAZARD_COST_MULT,))
            else:
                toward.append(arc + (tt * A.TOWARD_COST_MULT,))
        else:
            away.append(arc + (tt,))

    exit_idx = [index[e] for e in exits if e in index]
    n = len(node_ids)
    arcs = away
    ok = _reaches_exit(n, [a[0] for a in arcs], [a[1] for a in arcs], exit_idx)
    relaxed = False
    if not ok.all() and toward:
        arcs = away + toward
        relaxed = True
        ok = _reaches_exit(n, [a[0] for a in arcs], [a[1] for a in arcs], exit_idx)

    zone_arr = np.array([in_zone[nid] for nid in node_ids])
    arr = np.array(arcs, dtype=float) if arcs else np.zeros((0, 6))
    return EvacGraph(
        node_ids=node_ids, index=index,
        tails=arr[:, 0].astype(np.int64), heads=arr[:, 1].astype(np.int64),
        cap_vph=arr[:, 2], tt_s=arr[:, 3], edge_id=arr[:, 4].astype(np.int64), cost_s=arr[:, 5],
        exits=exit_idx, in_zone=zone_arr, relaxed=relaxed,
        unreachable={node_ids[i] for i in np.flatnonzero(~ok)},
    )
