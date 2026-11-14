"""Evacuate vs. shelter in place.

For each block in the zone: if the plume arrives before the block could get out, sheltering indoors
is safer than driving into the cloud. Blocks outside the zone are "outside".
"""
from __future__ import annotations

import numpy as np

from engine import assumptions as A

OUTSIDE, SHELTER, EVACUATE = "outside", "shelter", "evacuate"


def estimate_exit_s(ff_to_exit_s: np.ndarray, depart_s: np.ndarray | float = A.MOBILIZATION_S) -> np.ndarray:
    """Expected time to reach safety = departure + free-flow time × congestion factor."""
    return np.asarray(depart_s, float) + np.asarray(ff_to_exit_s, float) * A.CONGESTION_FACTOR


def decide(in_zone: np.ndarray, plume_arrival_s: np.ndarray, est_exit_s: np.ndarray) -> np.ndarray:
    """Vectorized decision per block. Unreachable blocks (est_exit = inf) shelter."""
    in_zone = np.asarray(in_zone, bool)
    arr = np.asarray(plume_arrival_s, float)
    est = np.asarray(est_exit_s, float)
    out = np.full(in_zone.shape, OUTSIDE, dtype=object)
    shelter = in_zone & ~(est < arr)          # also catches inf / NaN
    out[in_zone] = EVACUATE
    out[shelter] = SHELTER
    return out


def walk_time_s(walk_dist_m: np.ndarray, age65_share: np.ndarray) -> np.ndarray:
    speed = A.WALK_SPEED_MPS * (1 - age65_share) + A.WALK_SPEED_65_MPS * age65_share
    return np.asarray(walk_dist_m, float) / speed
