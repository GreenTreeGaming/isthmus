"""Bottlenecks, clearance time and route assignment.

Units: road capacity is a RATE (veh/h) but supply is a COUNT (vehicles). For a candidate duration T,
each road can carry capacity_vph × T / 3600 vehicles. The smallest T for which max-flow moves every
evacuating vehicle to an exit is the capacity-limited clearance time ("quickest transshipment"
approximation). Bottlenecks are the roads in the min cut just below that T — the cut that binds.
Routes come from min-cost flow at that T, decomposed into per-origin paths.

Uses OR-Tools' C++ max-flow / min-cost-flow (same algorithms as networkx, ~100× faster).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from ortools.graph.python import max_flow, min_cost_flow

from engine import assumptions as A


@dataclass
class Path:
    origin: int              # node index
    arcs: list[int]          # road arc indices, in order
    vehicles: float
    tt_s: float              # free-flow travel time along the path


@dataclass
class FlowResult:
    clearance_cap_s: float                   # capacity-limited T*
    clearance_s: float                       # T* + longest assigned free-flow path
    arc_flow: np.ndarray                     # vehicles per road arc
    bottleneck_arcs: list[int]               # road arc indices in the binding min cut
    paths: list[Path] = field(default_factory=list)
    total_vehicles: int = 0


def _caps(cap_vph: np.ndarray, T: float) -> np.ndarray:
    return np.floor(cap_vph * T / 3600.0).astype(np.int64)


def solve_flow(n: int, tails: np.ndarray, heads: np.ndarray, cap_vph: np.ndarray, cost_s: np.ndarray,
               tt_s: np.ndarray, exits: list[int], supply: dict[int, int]) -> FlowResult:
    m = len(tails)
    supply = {o: int(s) for o, s in supply.items() if s > 0}
    D = sum(supply.values())
    if D == 0 or m == 0:
        return FlowResult(0.0, 0.0, np.zeros(m), [], [], 0)

    S, T_node = n, n + 1
    big = D + 1
    origins = np.array(list(supply), dtype=np.int64)
    exits_arr = np.array(exits, dtype=np.int64)

    # ---- max-flow graph, reused across the binary search
    mf = max_flow.SimpleMaxFlow()
    road = mf.add_arcs_with_capacity(tails.astype(np.int64), heads.astype(np.int64), np.zeros(m, np.int64))
    mf.add_arcs_with_capacity(exits_arr, np.full(len(exits_arr), T_node, np.int64), np.full(len(exits_arr), big, np.int64))
    mf.add_arcs_with_capacity(np.full(len(origins), S, np.int64), origins,
                              np.array([supply[o] for o in origins], np.int64))

    def flow_at(T: float) -> int:
        mf.set_arcs_capacity(road, _caps(cap_vph, T))
        if mf.solve(S, T_node) != mf.OPTIMAL:
            raise RuntimeError("max-flow failed")
        return mf.optimal_flow()

    hi = 1800.0
    while flow_at(hi) < D:
        hi *= 2
        if hi > A.MAX_CLEARANCE_S:
            raise RuntimeError("evacuation infeasible within MAX_CLEARANCE_S — some origin cannot reach an exit")
    lo = 0.0
    while hi - lo > A.CLEARANCE_TOLERANCE_S:
        mid = (lo + hi) / 2
        if flow_at(mid) >= D:
            hi = mid
        else:
            lo = mid

    # ---- binding cut just below T*
    bottlenecks: list[int] = []
    if lo > 0 and flow_at(lo) < D:
        src_side = set(mf.get_source_side_min_cut())
        for a in range(m):
            if tails[a] in src_side and heads[a] not in src_side and cap_vph[a] > 0:
                bottlenecks.append(a)

    # ---- min-cost routing. At exactly T* every road is needed, which can force long detours;
    # a little slack often lowers total clearance (T + longest route). Try a few, keep the best.
    best = None
    for slack in A.ROUTING_SLACK_FACTORS:
        got = _route(n, tails, heads, cap_vph, cost_s, tt_s, exits, exits_arr, origins, supply, D, hi * slack)
        if got is None:
            continue
        T_used, arc_flow, paths = got
        total = T_used + max((p.tt_s for p in paths), default=0.0)
        if best is None or total < best[0]:
            best = (total, T_used, arc_flow, paths)
    if best is None:
        raise RuntimeError("min-cost flow failed")
    total, T_used, arc_flow, paths = best
    bottlenecks.sort(key=lambda a: -arc_flow[a])
    return FlowResult(clearance_cap_s=T_used, clearance_s=total, arc_flow=arc_flow,
                      bottleneck_arcs=bottlenecks, paths=paths, total_vehicles=D)


def _route(n, tails, heads, cap_vph, cost_s, tt_s, exits, exits_arr, origins, supply, D, T):
    """Min-cost flow with capacities for duration T (bumped if integer rounding makes it infeasible)."""
    T_node = n + 1
    costs = np.maximum(1, np.rint(cost_s)).astype(np.int64)
    for _ in range(6):
        mcf = min_cost_flow.SimpleMinCostFlow()
        mcf.add_arcs_with_capacity_and_unit_cost(tails.astype(np.int64), heads.astype(np.int64),
                                                 _caps(cap_vph, T), costs)
        mcf.add_arcs_with_capacity_and_unit_cost(
            exits_arr, np.full(len(exits_arr), T_node, np.int64),
            np.full(len(exits_arr), D, np.int64), np.zeros(len(exits_arr), np.int64))
        mcf.set_nodes_supplies(np.concatenate([origins, [T_node]]).astype(np.int64),
                               np.array([supply[o] for o in origins] + [-D], np.int64))
        if mcf.solve() == mcf.OPTIMAL:
            arc_flow = np.array([mcf.flow(a) for a in range(len(tails))], dtype=float)
            return T, arc_flow, decompose(n, tails, heads, arc_flow, tt_s, supply, set(exits))
        T *= 1.1
    return None


def decompose(n: int, tails, heads, arc_flow: np.ndarray, tt_s, supply: dict[int, int], exits: set[int]) -> list[Path]:
    """Split an edge flow into origin → exit paths (standard flow decomposition)."""
    out: list[list[int]] = [[] for _ in range(n)]
    for a in np.flatnonzero(arc_flow > 0):
        out[tails[a]].append(int(a))
    rem = arc_flow.copy()
    paths: list[Path] = []
    for o, s in supply.items():
        left = float(s)
        while left > 1e-9:
            u, arcs, seen, amount = o, [], {o}, left
            while u not in exits:
                nxt = next((a for a in out[u] if rem[a] > 1e-9), None)
                if nxt is None:
                    break
                arcs.append(nxt)
                amount = min(amount, rem[nxt])
                u = int(heads[nxt])
                if u in seen:          # defensive: optimal min-cost flow has no positive cycles
                    break
                seen.add(u)
            if u not in exits or not arcs:
                break
            for a in arcs:
                rem[a] -= amount
            paths.append(Path(origin=o, arcs=arcs, vehicles=amount, tt_s=float(sum(tt_s[a] for a in arcs))))
            left -= amount
    return paths
