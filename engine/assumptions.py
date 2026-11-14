"""Every tunable number in the engine lives here — one place, shown in the app's Assumptions tab.

Change a value here and every module picks it up. Keep units in the name.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- roads
# Per-lane flow capacity (vehicles / hour / lane) by OSM highway class.
# Highways ~1800 (HCM freeway basic segment); signalized city streets ~800.
LANE_CAPACITY_VPH: dict[str, float] = {
    "motorway": 1800,
    "trunk": 1600,
    "primary": 900,
    "secondary": 800,
    "tertiary": 700,
    "unclassified": 600,
    "residential": 500,
    "living_street": 300,
    "service": 300,
}
LINK_CAPACITY_VPH = 1200          # *_link ramps
DEFAULT_LANE_CAPACITY_VPH = 600   # unknown class

DEFAULT_SPEED_KPH: dict[str, float] = {
    "motorway": 100,
    "trunk": 80,
    "primary": 56,      # 35 mph
    "secondary": 48,    # 30 mph
    "tertiary": 40,
    "unclassified": 40,
    "residential": 40,  # 25 mph
    "living_street": 16,
    "service": 16,
}
DEFAULT_SPEED_FALLBACK_KPH = 40

DEFAULT_LANES: dict[str, int] = {
    "motorway": 2,
    "trunk": 2,
    "primary": 2,
    "secondary": 1,
    "tertiary": 1,
}
DEFAULT_LANES_FALLBACK = 1

# Road classes whose lanes can all be turned outbound when contraflow is on.
CONTRAFLOW_CLASSES: frozenset[str] = frozenset(
    {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link"}
)

# --------------------------------------------------------------------------- people
WALK_SPEED_MPS = 1.2              # typical pedestrian
WALK_SPEED_65_MPS = 0.8           # older residents
WALK_DETOUR_FACTOR = 1.3          # street distance ÷ straight-line distance
VEHICLES_PER_HOUSEHOLD = 1.0      # cars actually taken per car-owning household
DEFAULT_HOUSEHOLD_SIZE = 2.2      # used when households are missing
VISITOR_DRIVE_SHARE = 0.6         # daytime workers / game-day fans who drove in
VISITOR_OCCUPANCY = 1.8           # people per visitor vehicle
# Share of car-free residents who need a bus = disability_share + this × age65_share (capped at 1).
AGE65_NEED_BUS_WEIGHT = 0.5

# --------------------------------------------------------------------------- timing
MOBILIZATION_S = 300              # alert → first cars moving (5 min)
WAVE_INTERVAL_S = 600             # spacing between departure waves (10 min)
CONGESTION_FACTOR = 1.5           # free-flow → expected travel time, for the evacuate/shelter call
SIM_STEP_S = 30                   # queue simulation time step
MAX_SIM_S = 6 * 3600              # stop simulating after 6 h
MAX_CLEARANCE_S = 48 * 3600       # binary-search ceiling
CLEARANCE_TOLERANCE_S = 30        # binary-search precision
ROUTING_SLACK_FACTORS = (1.0, 1.1, 1.25, 1.5, 2.0, 3.0)  # route at T*×f, keep f minimizing T + longest route
DECISION_REFINE_ITERS = 2         # re-check evacuate/shelter after waves are assigned

# --------------------------------------------------------------------------- hazard
EXIT_BUFFER_M = 300               # safe exits sit this far beyond the protective zone
AWAY_TOLERANCE_M = 25             # an edge counts as "away" unless it gets this much closer
HAZARD_COST_MULT = 5.0            # routing cost multiplier for edges inside the zone
TOWARD_COST_MULT = 20.0           # fallback: toward-release edges, only if a node has no other way out

# ERG Table 1 style distances, used only if the erg_distances table is missing.
# APPROXIMATE — verify against the current DOT Emergency Response Guidebook before the demo.
# key: (chemical, spill_size, day|night) -> (isolation_m, protect_m)
ERG_FALLBACK: dict[tuple[str, str, str], tuple[float, float]] = {
    ("chlorine", "small", "day"): (60, 300),
    ("chlorine", "small", "night"): (60, 1100),
    ("chlorine", "large", "day"): (500, 3000),
    ("chlorine", "large", "night"): (500, 7900),
    ("ammonia", "small", "day"): (30, 100),
    ("ammonia", "small", "night"): (30, 200),
    ("ammonia", "large", "day"): (150, 800),
    ("ammonia", "large", "night"): (150, 2300),
}

# --------------------------------------------------------------------------- buses
BUS_DISPATCH_DELAY_S = 600        # alert → buses leave the garage (find drivers)
STOP_FIXED_S = 60                 # dwell per pickup stop
BOARDING_S_PER_PERSON = 6         # mobility-limited riders, per person
NURSING_BOARDING_S_PER_PERSON = 30
BUS_ZONE_COST_MULT = 3.0          # buses avoid driving inside the zone unless picking up
MAX_STOP_WALK_M = 400             # farther than this from a Metro stop → pick up at the block itself
BUS_SOLVER_TIME_LIMIT_S = 0.5     # OR-Tools search budget (interactive; batch uses 0.3)
UNSERVED_PENALTY_PER_PERSON = 100_000

# --------------------------------------------------------------------------- projection
METRIC_CRS = "EPSG:32616"         # UTM 16N — meters, covers Madison
