"""Engine contract — the ONE function every other part calls.

Implemented by engine/ (Claude B). Called by:
  - backend/  (FastAPI /simulate)       -> one scenario, must return in < 5 s
  - data/     (Databricks batch runs)   -> hundreds of scenarios via applyInPandas

Do not change without the contract owner's approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Chemical = Literal["chlorine", "ammonia"]
SpillSize = Literal["small", "large"]
TimeOfDay = Literal["night", "day", "gameday"]
Decision = Literal["evacuate", "shelter", "outside"]
HazardType = Literal["chemical", "flood"]
FloodSource = Literal["mendota", "monona", "both"]


@dataclass(frozen=True)
class ScenarioParams:
    release_lon: float                    # chemical: derailment point. flood: ignored (send any point)
    release_lat: float
    chemical: Chemical = "chlorine"
    spill_size: SpillSize = "large"
    wind_from_deg: float = 270.0          # meteorological: direction wind comes FROM, 0 = north
    wind_speed_mps: float = 4.0
    time_of_day: TimeOfDay = "day"
    compliance: float = 0.85              # share of evacuate-zone residents who actually leave
    bus_count: int = 20
    bus_capacity: int = 60
    contraflow: bool = False
    closed_edge_ids: tuple[int, ...] = ()
    seed: int = 0                         # for any randomness, so batch runs are reproducible
    # --- hazard type. "chemical" uses release point, chemical, spill and wind. "flood" uses the fields below.
    hazard: HazardType = "chemical"
    flood_source: FloodSource = "both"    # which lake rises: Mendota, Monona (+ Yahara River below it), or both
    flood_rise_m: float = 1.0             # how far the lake(s) rise above their normal level at the peak
    flood_peak_h: float = 6.0             # hours from the alert until the water peaks (rises linearly)


@dataclass
class BlockResult:
    block_id: str
    decision: Decision
    plume_arrival_s: float | None         # when the hazard arrives (gas, or flood water); None if it never does
    est_exit_time_s: float | None
    wave: int | None                      # departure wave index (0 = first), None if not evacuating
    drivers: float
    walkers: float
    need_bus: float


@dataclass
class EdgeLoad:
    edge_id: int
    flow_veh: float                       # vehicles assigned over the whole evacuation
    peak_load_ratio: float                # max (queue+flow)/capacity seen in the sim
    congested_at_s: float | None          # first time the edge backs up, None if never
    is_bottleneck: bool                   # in the min cut


@dataclass
class BusRoute:
    bus_id: int
    stops: list[str]                      # pickup_id / depot_id sequence, starts at a bus_garage
    arrival_s: list[float]                # arrival time at each stop
    load: list[int]                       # people on board after each stop
    path_node_ids: list[int]              # full node path for drawing
    deadline_s: list[float | None] = field(default_factory=list)
    # per stop: the gas-arrival deadline the router enforced (None for garage/shelter).
    # Use this for "gas at" / LATE in the UI so it always agrees with need_bus_unserved.


@dataclass
class Summary:
    clearance_time_s: float               # minimum T where all evacuating vehicles reach an exit
    people_evacuating: float
    people_sheltering: float
    need_bus_total: float
    need_bus_unserved: float              # not picked up before plume arrival
    bottleneck_edge_ids: list[int]
    runtime_ms: float
    sim_clearance_s: float = 0.0          # traffic sim: alert → last car out (includes mobilization + waves).
                                          # clearance_time_s above is the flow plan's driving time only.


@dataclass
class FloodStep:
    t_s: float                            # time since the alert
    rise_m: float                         # lake rise above normal at that time
    wkt: str                              # flooded land at that time, WGS84 (cumulative)


@dataclass
class ScenarioResult:
    params: ScenarioParams
    isolation_zone_wkt: str               # chemical: circle, WGS84. flood: "" (none)
    protect_zone_wkt: str                 # chemical: downwind polygon. flood: all land flooded at the peak. WGS84
    blocks: list[BlockResult]
    edges: list[EdgeLoad]                 # only edges with flow > 0 or bottlenecks
    buses: list[BusRoute]
    summary: Summary
    load_timeline: dict[int, list[float]] = field(default_factory=dict)
    # edge_id -> load ratio per sim step (step = SIM_STEP_S in assumptions). Optional, for animation.
    flood_source_wkt: str = ""            # flood only: the lake(s) that rise, WGS84
    flood_steps: list[FloodStep] = field(default_factory=list)   # flood only: water extent over time


def load_network(data_dir: str) -> object:
    """Load silver tables from data_dir and build/pickle the graph. Call once, reuse."""
    raise NotImplementedError


def run_scenario(params: ScenarioParams, network: object) -> ScenarioResult:
    """Run one full scenario: hazard -> decisions -> flow -> waves -> sim -> buses."""
    raise NotImplementedError
