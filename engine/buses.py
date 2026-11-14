"""Bus pickups for people who can't get out on their own (OR-Tools capacitated routing with deadlines).

- Buses leave the garage BUS_DISPATCH_DELAY_S after the alert and unload at the shelter.
- Travel times are congested times from the traffic simulation, not free-flow.
- Each pickup must be reached before the plume arrives there (time window).
- Buses avoid driving through the zone unless a pickup requires it (cost multiplier).
- Stops larger than one bus are split into bus-sized chunks.
- One trip per bus (multiple trips is a stretch goal). Pickups that can't be reached in time are
  dropped and reported as unserved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from contracts.engine_api import BusRoute
from engine import assumptions as A

UNREACHABLE = 10**7


@dataclass
class Stop:
    stop_id: str
    node_id: int
    people: int
    deadline_s: float
    board_s_per_person: float | None = None

    def __post_init__(self):
        if self.board_s_per_person is None:
            self.board_s_per_person = A.BOARDING_S_PER_PERSON


@dataclass
class BusPlan:
    routes: list[BusRoute]
    served: float
    unserved: float


class _LazyPaths:
    """Node paths rebuilt on demand from a predecessor matrix (only for legs buses actually drive)."""

    def __init__(self, pred, nodes, key_idx):
        self.pred, self.nodes, self.key_idx = pred, nodes, key_idx

    def get(self, ij, default=None):
        i, j = ij
        s, t = self.key_idx[i], self.key_idx[j]
        if s == t:
            return [self.nodes[s]]
        row = self.pred[i]
        if row[t] < 0:
            return default
        seq = [t]
        while seq[-1] != s:
            seq.append(int(row[seq[-1]]))
        return [self.nodes[x] for x in reversed(seq)]


def _paths_between(G: nx.DiGraph, keys: list[int], cost, time):
    """Time matrix + node paths between key nodes; paths chosen by cost, timed by time.

    Uses scipy's compiled Dijkstra when available (~50× faster on city-sized graphs), else networkx.
    """
    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
    except ImportError:
        return _paths_between_nx(G, keys, cost, time)

    nodes = list(G.nodes)
    index = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    rows, cols, cs, ts = [], [], [], []
    for u, v, d in G.edges(data=True):
        c = cost(u, v, d)
        if c is None:
            continue
        rows.append(index[u]); cols.append(index[v]); cs.append(max(c, 1e-6)); ts.append(time(u, v, d))
    rows, cols = np.asarray(rows, np.int64), np.asarray(cols, np.int64)
    graph = csr_matrix((np.asarray(cs), (rows, cols)), shape=(n, n))
    key_idx = [index[k] for k in keys]
    dist, pred = dijkstra(graph, directed=True, indices=key_idx, return_predecessors=True)

    # Time along each cost-optimal tree: pointer-jumping sum of edge times up to the source.
    ekey = rows * n + cols
    order = np.argsort(ekey)
    ekey, etime = ekey[order], np.asarray(ts)[order]
    valid = pred >= 0
    w = np.zeros(pred.shape)
    q = pred[valid].astype(np.int64) * n + np.nonzero(valid)[1]
    w[valid] = etime[np.searchsorted(ekey, q)]
    acc, par = w, np.where(valid, pred, -1)
    while (par >= 0).any():
        has = par >= 0
        safe = np.where(has, par, 0)
        acc = np.where(has, acc + np.take_along_axis(acc, safe, axis=1), acc)
        par = np.where(has, np.take_along_axis(par, safe, axis=1), -1)
    tmat = acc[:, key_idx]
    tmat[~np.isfinite(dist[:, key_idx])] = UNREACHABLE
    return tmat.tolist(), _LazyPaths(pred, nodes, key_idx)


def _paths_between_nx(G: nx.DiGraph, keys: list[int], cost, time) -> tuple[list[list[float]], dict]:
    """Fallback without scipy."""
    k = len(keys)
    mat = [[0.0] * k for _ in range(k)]
    paths: dict[tuple[int, int], list[int]] = {}
    for i, s in enumerate(keys):
        pred, _ = nx.dijkstra_predecessor_and_distance(G, s, weight=cost)
        for j, t in enumerate(keys):
            if i == j:
                paths[(i, j)] = [s]
                continue
            if t not in pred:
                mat[i][j] = UNREACHABLE
                continue
            seq = [t]
            while seq[-1] != s:
                seq.append(pred[seq[-1]][0])
            seq.reverse()
            mat[i][j] = sum(time(seq[x], seq[x + 1], G.edges[seq[x], seq[x + 1]]) for x in range(len(seq) - 1))
            paths[(i, j)] = seq
    return mat, paths


def plan_buses(G: nx.DiGraph, edge_time_s: dict[int, float], zone_edge_ids: set[int], closed_edge_ids: set[int],
               garage: tuple[str, int], shelter: tuple[str, int], stops: list[Stop],
               bus_count: int, bus_capacity: int, dispatch_s: float | None = None,
               time_limit_s: float | None = None) -> BusPlan:
    dispatch_s = A.BUS_DISPATCH_DELAY_S if dispatch_s is None else dispatch_s
    time_limit_s = A.BUS_SOLVER_TIME_LIMIT_S if time_limit_s is None else time_limit_s
    total = float(sum(s.people for s in stops))
    if not stops or bus_count <= 0 or bus_capacity <= 0:
        return BusPlan([], 0.0, total)

    def time(u, v, d):
        return edge_time_s.get(d["edge_id"], d["travel_time_s"])

    def cost(u, v, d):
        if d["edge_id"] in closed_edge_ids:
            return None
        t = time(u, v, d)
        return t * A.BUS_ZONE_COST_MULT if d["edge_id"] in zone_edge_ids else t

    # split oversized stops into bus-sized chunks
    chunks: list[Stop] = []
    for s in stops:
        left = s.people
        while left > 0:
            take = min(left, bus_capacity)
            chunks.append(Stop(s.stop_id, s.node_id, take, s.deadline_s, s.board_s_per_person))
            left -= take

    keys = [garage[1], shelter[1]] + [c.node_id for c in chunks]
    uniq = list(dict.fromkeys(keys))
    pos = {n: i for i, n in enumerate(uniq)}
    umat, upaths = _paths_between(G, uniq, cost, time)

    def tmat(i, j):
        return umat[pos[keys[i]]][pos[keys[j]]]

    # drop chunks that can't possibly be reached in time
    feasible = [i for i in range(2, len(keys))
                if dispatch_s + tmat(0, i) <= chunks[i - 2].deadline_s and tmat(i, 1) < UNREACHABLE]
    unserved = sum(chunks[i - 2].people for i in range(2, len(keys)) if i not in set(feasible))
    if not feasible:
        return BusPlan([], 0.0, float(unserved))

    model_nodes = [0, 1] + feasible                       # model index -> keys index
    N = len(model_nodes)
    service = [0, 0] + [A.STOP_FIXED_S + chunks[i - 2].people * chunks[i - 2].board_s_per_person for i in feasible]
    demand = [0, 0] + [chunks[i - 2].people for i in feasible]
    horizon = int(A.MAX_SIM_S * 2)

    manager = pywrapcp.RoutingIndexManager(N, bus_count, [0] * bus_count, [1] * bus_count)
    routing = pywrapcp.RoutingModel(manager)

    def transit(fi, ti):
        a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
        return int(min(tmat(model_nodes[a], model_nodes[b]), UNREACHABLE) + service[a])

    cb = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(cb)
    routing.AddDimension(cb, 0, horizon, False, "Time")
    tdim = routing.GetDimensionOrDie("Time")
    dcb = routing.RegisterUnaryTransitCallback(lambda fi: demand[manager.IndexToNode(fi)])
    routing.AddDimensionWithVehicleCapacity(dcb, 0, [bus_capacity] * bus_count, True, "Load")
    ldim = routing.GetDimensionOrDie("Load")

    for v in range(bus_count):
        tdim.CumulVar(routing.Start(v)).SetRange(int(dispatch_s), int(dispatch_s))
    for m in range(2, N):
        idx = manager.NodeToIndex(m)
        tdim.CumulVar(idx).SetMax(int(chunks[model_nodes[m] - 2].deadline_s))
        routing.AddDisjunction([idx], int(A.UNSERVED_PENALTY_PER_PERSON * demand[m]))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(time_limit_s * 1000))
    sol = routing.SolveWithParameters(params)
    if sol is None:
        return BusPlan([], 0.0, total)

    routes: list[BusRoute] = []
    served = 0.0
    for v in range(bus_count):
        idx = routing.Start(v)
        seq = []
        while True:
            m = manager.IndexToNode(idx)
            seq.append((m, sol.Value(tdim.CumulVar(idx)), sol.Value(ldim.CumulVar(idx))))
            if routing.IsEnd(idx):
                break
            idx = sol.Value(routing.NextVar(idx))
        if len(seq) <= 2:
            continue
        stops_out, arrive, load, path, deadlines = [], [], [], [], []
        for x, (m, t, l) in enumerate(seq):
            ki = model_nodes[m]
            if m == 0:
                stops_out.append(garage[0]); load.append(0); deadlines.append(None)
            elif m == 1:
                stops_out.append(shelter[0]); load.append(0); deadlines.append(None)
            else:
                stops_out.append(chunks[ki - 2].stop_id); load.append(int(l + demand[m]))
                deadlines.append(float(chunks[ki - 2].deadline_s))
                served += demand[m]
            arrive.append(float(t))
            if x + 1 < len(seq):
                nk = model_nodes[seq[x + 1][0]]
                seg = upaths.get((pos[keys[ki]], pos[keys[nk]]), [])
                path.extend(seg if not path else seg[1:])
        routes.append(BusRoute(bus_id=v, stops=stops_out, arrival_s=arrive, load=load, path_node_ids=path,
                                  deadline_s=deadlines))

    return BusPlan(routes=routes, served=served, unserved=max(0.0, total - served))


def to_people(x: float) -> int:
    return int(math.ceil(x - 1e-9)) if x > 0 else 0
