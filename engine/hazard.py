"""Hazard zone from ERG distances: isolation circle + downwind protective-action square.

ERG geometry: the protective action zone is a square whose side equals the downwind distance,
with the release point at the middle of its upwind edge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely

from engine import assumptions as A
from engine.network import Network, to_lonlat, to_metric


@dataclass
class Hazard:
    rx: float                      # release, meters
    ry: float
    ux: float                      # downwind unit vector (direction the gas travels)
    uy: float
    wind_speed_mps: float
    isolation_m: float
    protect_m: float
    isolation: shapely.Polygon     # metric
    protect: shapely.Polygon       # metric
    zone: shapely.Geometry         # isolation ∪ protect, metric
    region: shapely.Geometry       # zone buffered by EXIT_BUFFER_M — exits sit outside this

    def in_zone(self, x, y) -> np.ndarray:
        return shapely.contains_xy(self.zone, np.asarray(x, float), np.asarray(y, float))

    def in_region(self, x, y) -> np.ndarray:
        return shapely.contains_xy(self.region, np.asarray(x, float), np.asarray(y, float))

    def distance(self, x, y) -> np.ndarray:
        return np.hypot(np.asarray(x, float) - self.rx, np.asarray(y, float) - self.ry)

    def downwind(self, x, y) -> np.ndarray:
        return (np.asarray(x, float) - self.rx) * self.ux + (np.asarray(y, float) - self.ry) * self.uy

    def arrival_s(self, x, y) -> np.ndarray:
        """Plume arrival time (s) at each point; NaN outside the zone.

        Gas travels with the wind, so arrival = straight-line distance from release / wind speed.
        """
        x, y = np.asarray(x, float), np.asarray(y, float)
        t = self.distance(x, y) / max(self.wind_speed_mps, 0.1)
        return np.where(self.in_zone(x, y), t, np.nan)

    def wkt_lonlat(self) -> tuple[str, str]:
        def f(x, y):
            return to_lonlat(x, y)
        return (shapely.transform(self.isolation, f, interleaved=False).wkt,
                shapely.transform(self.protect, f, interleaved=False).wkt)


def erg_distances(net: Network, chemical: str, spill_size: str, time_of_day: str,
                  wind_speed_mps: float = 0.0) -> tuple[float, float]:
    """(isolation_m, protect_m). Low-wind values from the silver table (or ERG fallback), then large spills are
    scaled to the ERG Table 3 wind band, so stronger wind → shorter protective distance."""
    tod = "night" if time_of_day == "night" else "day"
    key = (chemical, spill_size, tod)
    if key in net.erg:
        iso, prot = net.erg[key]
    elif key in A.ERG_FALLBACK:
        iso, prot = A.ERG_FALLBACK[key]
    else:
        raise KeyError(f"no ERG distances for {key}")
    return iso, prot * A.erg_wind_factor(chemical, spill_size, tod, wind_speed_mps)


def build_hazard(net: Network, release_lon: float, release_lat: float, chemical: str, spill_size: str,
                 time_of_day: str, wind_from_deg: float, wind_speed_mps: float) -> Hazard:
    iso_m, prot_m = erg_distances(net, chemical, spill_size, time_of_day, wind_speed_mps)
    rx, ry = to_metric(release_lon, release_lat)
    toward = math.radians((wind_from_deg + 180.0) % 360.0)   # meteorological FROM → travel direction
    ux, uy = math.sin(toward), math.cos(toward)               # 0° = north, clockwise
    px, py = -uy, ux                                          # crosswind unit vector

    isolation = shapely.Point(rx, ry).buffer(iso_m, quad_segs=16)
    half = prot_m / 2.0
    corners = [
        (rx + px * half, ry + py * half),
        (rx + px * half + ux * prot_m, ry + py * half + uy * prot_m),
        (rx - px * half + ux * prot_m, ry - py * half + uy * prot_m),
        (rx - px * half, ry - py * half),
    ]
    protect = shapely.Polygon(corners)
    zone = shapely.union(isolation, protect)
    region = zone.buffer(A.EXIT_BUFFER_M)
    shapely.prepare(zone)
    shapely.prepare(region)
    return Hazard(rx=rx, ry=ry, ux=ux, uy=uy, wind_speed_mps=wind_speed_mps, isolation_m=iso_m,
                  protect_m=prot_m, isolation=isolation, protect=protect, zone=zone, region=region)
