"""Departure waves.

Priority: earliest plume arrival first (bucketed to the wave interval), then — within a bucket —
blocks closest to an exit first, so downstream blocks clear the road before upstream blocks that must
drive through them.

Capacity: each wave may push at most capacity_vph × WAVE_INTERVAL_S / 3600 vehicles through every
bottleneck and exit link. An origin starts in the first wave that still has room on all its key links.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from engine import assumptions as A
from engine.flow import Path


def assign_waves(origins: list[int], arrival_s: dict[int, float], ff_to_exit_s: dict[int, float],
                 paths: list[Path], key_arcs: set[int], cap_vph: np.ndarray) -> dict[int, int]:
    by_origin: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for p in paths:
        for a in p.arcs:
            if a in key_arcs:
                by_origin[p.origin][a] += p.vehicles

    def priority(o: int):
        arr = arrival_s.get(o, math.inf)
        bucket = math.floor(arr / A.WAVE_INTERVAL_S) if math.isfinite(arr) else math.inf
        return (bucket, ff_to_exit_s.get(o, math.inf), o)

    per_wave = cap_vph * A.WAVE_INTERVAL_S / 3600.0
    used: dict[int, float] = defaultdict(float)
    waves: dict[int, int] = {}
    for o in sorted(origins, key=priority):
        w = 0
        for a in by_origin.get(o, {}):
            if per_wave[a] > 0:
                w = max(w, int(used[a] // per_wave[a]))
        for a, v in by_origin.get(o, {}).items():
            used[a] += v
        waves[o] = w
    return waves


def departure_s(wave: int) -> float:
    return A.MOBILIZATION_S + wave * A.WAVE_INTERVAL_S
