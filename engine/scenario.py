"""run_scenario: hazard → decisions → flow → waves → sim → buses → ScenarioResult (contracts/engine_api.py)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd
import shapely

from contracts.engine_api import BlockResult, EdgeLoad, FloodStep, ScenarioParams, ScenarioResult, Summary
from engine import assumptions as A
from engine.buses import Stop, plan_buses, to_people
from engine.decisions import EVACUATE, SHELTER, decide, estimate_exit_s, walk_time_s
from engine.evacgraph import EvacGraph, build_evac_graph
from engine.flood import FloodHazard, build_flood_hazard
from engine.flow import FlowResult, solve_flow
from engine.hazard import Hazard, build_hazard
from engine.network import Network
from engine.population import facility_need_bus, split_population
from engine.sim import Group, simulate
from engine.waves import assign_waves, departure_s


@dataclass
class Diagnostics:
    flow_clearance_s: float = 0.0
    sim_clearance_s: float = 0.0
    capacity_time_s: float = 0.0
    relaxed_road_rules: bool = False
    refine_iterations: int = 0
    unreachable_nodes: int = 0
    vehicles: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)
    jam_edge_ids: list[int] = field(default_factory=list)   # top roads by queued vehicle-minutes (where traffic jams)


def run_scenario(params: ScenarioParams, network: Network) -> ScenarioResult:
    """Run one full scenario. See contracts/engine_api.py."""
    return run_with_diagnostics(params, network)[0]


def run_with_diagnostics(params: ScenarioParams, net: Network) -> tuple[ScenarioResult, Diagnostics]:
    t_start = time.perf_counter()
    diag = Diagnostics()
    lap = [t_start]

    def mark(name: str):
        now = time.perf_counter()
        diag.timings_ms[name] = round((now - lap[0]) * 1000, 1)
        lap[0] = now

    # ---- hazard + roads
    hz = make_hazard(net, params)
    eg = build_evac_graph(net, hz, params.closed_edge_ids, params.contraflow)
    diag.relaxed_road_rules, diag.unreachable_nodes = eg.relaxed, len(eg.unreachable)
    mark("hazard+graph")

    # ---- people
    pop = split_population(net.blocks, params.time_of_day)
    bx, by = net.blocks["x"].to_numpy(), net.blocks["y"].to_numpy()
    in_zone = hz.in_zone(bx, by)
    arrival = hz.arrival_s(bx, by)
    ff_node = eg.ff_time_to_exit()
    ff_block = np.array([ff_node[eg.index[n]] if n in eg.index else np.inf for n in pop["node_id"]])
    walk_m = shapely.distance(hz.region.boundary, shapely.points(bx, by)) * A.WALK_DETOUR_FACTOR
    walk_s = walk_time_s(walk_m, pop["age65_share"].to_numpy())
    has_cars = pop["vehicles"].to_numpy() >= 0.5
    est = np.where(has_cars, estimate_exit_s(ff_block), A.MOBILIZATION_S + walk_s)
    decision = decide(in_zone, arrival, est)
    mark("decisions")

    # ---- flow + waves, re-checking decisions against assigned departure times
    flow: FlowResult | None = None
    waves: dict[int, int] = {}
    for it in range(A.DECISION_REFINE_ITERS + 1):
        diag.refine_iterations = it
        flow, waves, node_tt = _plan(eg, pop, decision, arrival, ff_node, params.compliance)
        if it == A.DECISION_REFINE_ITERS:
            break
        changed = False
        for i in np.flatnonzero(decision == EVACUATE):
            n = int(pop.at[i, "node_id"])
            if n not in eg.index or not has_cars[i]:
                continue
            idx = eg.index[n]
            dep = departure_s(waves.get(idx, 0))
            if dep + node_tt.get(idx, ff_block[i]) * A.CONGESTION_FACTOR >= arrival[i]:
                decision[i] = SHELTER
                est[i] = dep + node_tt.get(idx, ff_block[i]) * A.CONGESTION_FACTOR
                changed = True
        if not changed:
            break
    diag.flow_clearance_s, diag.capacity_time_s, diag.vehicles = flow.clearance_s, flow.clearance_cap_s, flow.total_vehicles
    mark("flow+waves")

    # ---- traffic simulation
    groups = [Group(p.arcs, p.vehicles, departure_s(waves.get(p.origin, 0))) for p in flow.paths]
    sim = simulate(eg.cap_vph, eg.tt_s, groups)
    diag.sim_clearance_s = sim.clearance_s
    if sim.queue_veh_min is not None:
        top = np.argsort(-sim.queue_veh_min)[: A.JAM_TOP_N]
        diag.jam_edge_ids = [int(eg.edge_id[a]) for a in top if sim.queue_veh_min[a] >= A.JAM_MIN_VEH_MIN]
    mark("sim")

    # ---- buses
    bus_plan, need_total, nh_shelter, nh_evac, bus_shelter = _buses(
        net, hz, eg, sim, pop, decision, arrival, ff_node, params)
    mark("buses")

    # ---- assemble
    evac = decision == EVACUATE
    shel = decision == SHELTER
    comp = params.compliance
    people_evac = float(((pop["driver_people"] + pop["walkers"]) * comp + pop["need_bus"])[evac].sum()
                        - bus_shelter + nh_evac)
    people_shelter = float(pop["pop"][shel].sum() + nh_shelter + bus_shelter)

    blocks_out = []
    for i, row in enumerate(pop.itertuples(index=False)):
        d = decision[i]
        f = comp if d == EVACUATE else 1.0
        idx = eg.index.get(int(row.node_id))
        blocks_out.append(BlockResult(
            block_id=str(row.block_id),
            decision=d,
            plume_arrival_s=None if np.isnan(arrival[i]) else float(arrival[i]),
            est_exit_time_s=float(est[i]) if in_zone[i] and np.isfinite(est[i]) else None,
            wave=int(waves.get(idx, 0)) if d == EVACUATE else None,
            drivers=float(row.vehicles * f),
            walkers=float(row.walkers * f),
            need_bus=float(row.need_bus),
        ))

    bott = set(flow.bottleneck_arcs)
    edges_out, timeline = [], {}
    for a in range(len(eg.tails)):
        if flow.arc_flow[a] <= 0 and a not in bott:
            continue
        eid = int(eg.edge_id[a])
        ca = sim.congested_at_s[a]
        edges_out.append(EdgeLoad(edge_id=eid, flow_veh=float(flow.arc_flow[a]),
                                  peak_load_ratio=float(round(sim.peak_ratio[a], 3)),
                                  congested_at_s=None if np.isnan(ca) else float(ca),
                                  is_bottleneck=a in bott))
        if a in sim.timeline and any(sim.timeline[a]):
            timeline[eid] = sim.timeline[a]

    iso_wkt, prot_wkt = hz.wkt_lonlat()
    runtime_ms = (time.perf_counter() - t_start) * 1000
    summary = Summary(
        clearance_time_s=float(flow.clearance_s),
        people_evacuating=people_evac,
        people_sheltering=people_shelter,
        need_bus_total=float(need_total),
        need_bus_unserved=float(bus_plan.unserved),
        bottleneck_edge_ids=[int(eg.edge_id[a]) for a in flow.bottleneck_arcs],
        runtime_ms=round(runtime_ms, 1),
        sim_clearance_s=float(sim.clearance_s),
    )
    result = ScenarioResult(params=params, isolation_zone_wkt=iso_wkt, protect_zone_wkt=prot_wkt,
                            blocks=blocks_out, edges=edges_out, buses=bus_plan.routes, summary=summary,
                            load_timeline=timeline)
    if isinstance(hz, FloodHazard):
        result.flood_source_wkt = hz.grid.lake_wkt.get(hz.source, "")
        result.flood_steps = [FloodStep(t_s=t, rise_m=h, wkt=w) for t, h, w in hz.steps]
    return result, diag


def make_hazard(net: Network, params: ScenarioParams) -> Hazard | FloodHazard:
    """The danger zone and arrival times for this scenario: chemical gas zone (ERG) or lake flood."""
    if params.hazard == "flood":
        return build_flood_hazard(net, params.flood_source, params.flood_rise_m, params.flood_peak_h)
    return build_hazard(net, params.release_lon, params.release_lat, params.chemical, params.spill_size,
                        params.time_of_day, params.wind_from_deg, params.wind_speed_mps)


def _plan(eg: EvacGraph, pop: pd.DataFrame, decision: np.ndarray, arrival: np.ndarray,
          ff_node: np.ndarray, compliance: float):
    """Supply from evacuating blocks → flow → waves. Returns (flow, waves by node index, max path tt by node)."""
    evac = (decision == EVACUATE)
    df = pd.DataFrame({"node_id": pop["node_id"], "veh": pop["vehicles"] * compliance, "arr": arrival})[evac]
    df = df[df["node_id"].isin(eg.index.keys())]
    grouped = df.groupby("node_id").agg(veh=("veh", "sum"), arr=("arr", "min"))
    # Only nodes with a driving route out get vehicles. (A block can evacuate on foot while a fraction of a
    # car rounds up to 1 at a node with no drivable exit — those occupants walk out instead.)
    supply = {eg.index[int(n)]: int(math.ceil(v - 1e-9)) for n, v in grouped["veh"].items()
              if v > 0 and np.isfinite(ff_node[eg.index[int(n)]])}
    flow = solve_flow(eg.n, eg.tails, eg.heads, eg.cap_vph, eg.cost_s, eg.tt_s, eg.exits, supply)

    exits = set(eg.exits)
    key = set(flow.bottleneck_arcs) | {a for a in range(len(eg.heads)) if eg.heads[a] in exits}
    arr_by_idx = {eg.index[int(n)]: float(a) for n, a in grouped["arr"].items()}
    ff_by_idx = {i: float(ff_node[i]) for i in supply}
    waves = assign_waves(list(supply), arr_by_idx, ff_by_idx, flow.paths, key, eg.cap_vph)
    node_tt: dict[int, float] = {}
    for p in flow.paths:
        node_tt[p.origin] = max(node_tt.get(p.origin, 0.0), p.tt_s)
    return flow, waves, node_tt


def _buses(net: Network, hz: Hazard | FloodHazard, eg: EvacGraph, sim, pop: pd.DataFrame, decision, arrival, ff_node,
           params: ScenarioParams):
    G = net.G
    # congested travel time per edge (free-flow + average queue delay while buses are out)
    edge_time = {int(eg.edge_id[a]): float(eg.tt_s[a] + sim.mean_delay_s[a]) for a in range(len(eg.tails))}
    nodes = list(G.nodes)
    nz = dict(zip(nodes, hz.in_zone([G.nodes[n]["x"] for n in nodes], [G.nodes[n]["y"] for n in nodes])))
    if isinstance(hz, FloodHazard):
        from engine.flood import elevated_nodes
        nz.update({n: False for n in elevated_nodes(net)})
    zone_edges = {d["edge_id"] for u, v, d in G.edges(data=True) if nz[u] or nz[v]}

    garage, shelter = _depots(net, hz, eg)
    # earliest a bus could possibly reach each node (free-flow from the garage, then congestion factor)
    from_garage = nx.single_source_dijkstra_path_length(G, garage[1], weight="travel_time_s")

    def bus_can_make_it(node: int, deadline: float) -> bool:
        return A.BUS_DISPATCH_DELAY_S + from_garage.get(node, math.inf) * A.CONGESTION_FACTOR < deadline

    # residents who need a bus → nearest metro stop within walking range, else their own block.
    # If no bus could arrive before the gas, they shelter in place (not "unserved").
    stops: dict[str, Stop] = {}
    bus_shelter = 0.0
    metro = net.pickups[net.pickups["kind"] == "metro_stop"] if not net.pickups.empty else net.pickups
    mx, my = metro["x"].to_numpy(float), metro["y"].to_numpy(float)
    evac_idx = np.flatnonzero(decision == EVACUATE)
    for i in evac_idx:
        nb = float(pop.at[i, "need_bus"])
        if nb <= 0:
            continue
        if not bus_can_make_it(int(pop.at[i, "node_id"]), float(arrival[i])):
            bus_shelter += nb
            continue
        bxy = (net.blocks.at[i, "x"], net.blocks.at[i, "y"])
        d2 = (mx - bxy[0]) ** 2 + (my - bxy[1]) ** 2
        j = int(np.argmin(d2)) if len(metro) else -1
        if j >= 0 and d2[j] <= A.MAX_STOP_WALK_M ** 2 and bus_can_make_it(int(metro.iloc[j]["node_id"]), float(arrival[i])):
            sid, node = str(metro.iloc[j]["pickup_id"]), int(metro.iloc[j]["node_id"])
        else:
            sid, node = str(pop.at[i, "block_id"]), int(pop.at[i, "node_id"])
        s = stops.setdefault(sid, Stop(sid, node, 0, math.inf))
        s.people += nb                                    # float until rounded below
        s.deadline_s = min(s.deadline_s, float(arrival[i]))
    for s in stops.values():
        s.people = to_people(s.people)

    # nursing homes in the zone: bus if there's time, otherwise staff shelter residents in place
    nh_shelter = nh_evac = 0.0
    nh = facility_need_bus(net.facilities)
    for f in nh.itertuples(index=False):
        arr = float(hz.arrival_s(f.x, f.y))
        if math.isnan(arr) or f.need_bus <= 0:
            continue
        if not bus_can_make_it(int(f.node_id), arr):
            nh_shelter += f.need_bus
            continue
        nh_evac += f.need_bus
        stops[str(f.facility_id)] = Stop(str(f.facility_id), int(f.node_id), to_people(f.need_bus), arr,
                                         A.NURSING_BOARDING_S_PER_PERSON)

    stop_list = [s for s in stops.values() if s.people > 0]
    need_total = sum(s.people for s in stop_list)
    plan = plan_buses(G, edge_time, zone_edges, set(params.closed_edge_ids), garage, shelter, stop_list,
                      params.bus_count, params.bus_capacity)
    return plan, need_total, nh_shelter, nh_evac, bus_shelter


def _depots(net: Network, hz: Hazard | FloodHazard, eg: EvacGraph) -> tuple[tuple[str, int], tuple[str, int]]:
    d = net.depots
    far_exit = max(eg.exits, key=lambda i: float(hz.distance(*_xy(net, eg.node_ids[i])))) if eg.exits else None
    fallback = ("exit", eg.node_ids[far_exit]) if far_exit is not None else ("node", next(iter(net.G.nodes)))

    def pick(kind):
        rows = d[d["kind"] == kind] if not d.empty else d
        if len(rows):
            r = rows.iloc[0]
            return str(r["depot_id"]), int(r["node_id"])
        return fallback

    def pick_shelter():
        """Closest candidate shelter outside the danger area (zone + exit buffer); else the farthest one."""
        rows = d[d["kind"] == "shelter"] if not d.empty else d
        if not len(rows):
            return fallback
        x, y = rows["x"].to_numpy(float), rows["y"].to_numpy(float)
        dist = hz.geo_distance(x, y)
        safe = ~hz.in_region(x, y)
        i = int(np.argmin(np.where(safe, dist, np.inf))) if safe.any() else int(np.argmax(dist))
        r = rows.iloc[i]
        return str(r["depot_id"]), int(r["node_id"])

    return pick("bus_garage"), pick_shelter()


def _xy(net: Network, n: int):
    return net.G.nodes[n]["x"], net.G.nodes[n]["y"]
