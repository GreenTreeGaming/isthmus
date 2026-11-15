"""Lake-flood hazard: the lakes rise and water spreads over the land it can actually reach.

Built from data/silver/flood_grid.npz (data/flood_dem.py): for every ~20 m cell, how far each lake must rise
above its normal level before water connects to that cell (priority-flood on USGS 3DEP elevation).

A scenario raises the chosen lake(s) by `rise_m`, linearly over `peak_h` hours from the alert. Then:
- danger zone      = land whose rise-needed ≤ rise_m (it floods by the peak)
- arrival time     = peak_s × rise_needed / rise_m (when the rising water reaches that cell's height)
- "away"           = toward cells that need more rise (higher ground), so the road rules, departure waves,
                     traffic sim and bus routing run unchanged.
FloodHazard has the same interface as engine.hazard.Hazard.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage

from engine import assumptions as A
from engine.network import to_lonlat

SOURCES = {"mendota": ("mendota",), "monona": ("monona",), "both": ("mendota", "monona")}
LAKE_CODE = {"mendota": 1, "monona": 2}


def priority_flood(elev: np.ndarray, seeds: np.ndarray, blocked: np.ndarray) -> np.ndarray:
    """Lowest water level at which each cell connects to `seeds` (4-neighbour); inf if never."""
    H, W = elev.shape
    e, blk = elev.ravel(), blocked.ravel()
    level = np.full(H * W, np.inf)
    done = np.zeros(H * W, bool)
    pq = [(-np.inf, int(i)) for i in np.flatnonzero(seeds.ravel())]
    for _, i in pq:
        level[i] = -np.inf
    heapq.heapify(pq)
    while pq:
        lv, i = heapq.heappop(pq)
        if done[i]:
            continue
        done[i] = True
        r, c = divmod(i, W)
        for j in (i - W if r > 0 else -1, i + W if r < H - 1 else -1,
                  i - 1 if c > 0 else -1, i + 1 if c < W - 1 else -1):
            if j < 0 or done[j] or blk[j]:
                continue
            nl = max(lv, e[j])
            if nl < level[j]:
                level[j] = nl
                heapq.heappush(pq, (nl, j))
    return level.reshape(H, W)


@dataclass
class FloodGrid:
    x0: float                                   # UTM 16N of the top-left corner
    y_top: float
    cell: float
    lake_code: np.ndarray                       # 0 land, 1 Mendota, 2 Monona (+ Yahara below it)
    rise: dict[str, np.ndarray]                 # per source: rise needed (m) per cell, lakes filled from shore
    levels: dict[str, float]                    # normal lake level (m)
    lake_wkt: dict[str, str] = field(default_factory=dict)   # per source: lake outline, WGS84

    def rc(self, x, y):
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        r = np.floor((self.y_top - y) / self.cell).astype(int)
        c = np.floor((x - self.x0) / self.cell).astype(int)
        ok = (r >= 0) & (r < self.lake_code.shape[0]) & (c >= 0) & (c < self.lake_code.shape[1])
        return np.clip(r, 0, self.lake_code.shape[0] - 1), np.clip(c, 0, self.lake_code.shape[1] - 1), ok


def load_flood_grid(path: Path) -> FloodGrid | None:
    if not path.exists():
        return None
    z = np.load(path)
    lake = z["lake_code"].astype(np.int8)
    water = lake != 0
    # Points over a lake (bridges, causeways, shoreline nodes snapped into the water) take the rise of the
    # nearest land cell; land below the normal level that connects to the lake floods at the first rise.
    _, (ir, ic) = ndimage.distance_transform_edt(water, return_indices=True)
    raw = {k: z[f"rise_{k}"].astype(np.float32) for k in LAKE_CODE}
    raw["both"] = np.minimum(raw["mendota"], raw["monona"])
    rise = {}
    for k, r in raw.items():
        r = np.where(np.isfinite(r), np.maximum(r, A.FLOOD_MIN_RISE_M), np.inf).astype(np.float32)
        rise[k] = r[ir, ic]
    g = FloodGrid(x0=float(z["x0"]), y_top=float(z["y_top"]), cell=float(z["cell"]), lake_code=lake,
                  rise=rise, levels={k: float(z[f"level_{k}"]) for k in LAKE_CODE})
    for src, lakes in SOURCES.items():
        mask = np.isin(lake, [LAKE_CODE[k] for k in lakes])
        g.lake_wkt[src] = _lonlat_wkt(_polygonize(g, mask, simplify_m=40.0))
    return g


def _polygonize(g: FloodGrid, mask: np.ndarray, simplify_m: float = 15.0, factor: int = 1) -> shapely.Geometry:
    """Union of the cells in `mask` (run-length rows → rectangles), metric, lightly simplified.
    factor > 1 merges factor×factor cells first (coarser, faster — for map display)."""
    if not mask.any():
        return shapely.Polygon()
    cell = g.cell
    if factor > 1:
        H, W = (mask.shape[0] // factor) * factor, (mask.shape[1] // factor) * factor
        mask = mask[:H, :W].reshape(H // factor, factor, W // factor, factor).any(axis=(1, 3))
        cell = g.cell * factor
    rects = []
    pad = np.zeros((mask.shape[0], 1), bool)
    m = np.hstack([pad, mask, pad]).astype(np.int8)
    d = np.diff(m, axis=1)
    for r in np.flatnonzero(mask.any(axis=1)):
        starts, ends = np.flatnonzero(d[r] == 1), np.flatnonzero(d[r] == -1)
        y1 = g.y_top - r * cell
        for s, e in zip(starts, ends):
            rects.append(shapely.box(g.x0 + s * cell, y1 - cell, g.x0 + e * cell, y1))
    geom = shapely.union_all(rects, grid_size=0.01)
    return geom.simplify(simplify_m) if simplify_m else geom


def _lonlat_wkt(geom: shapely.Geometry) -> str:
    if geom.is_empty:
        return ""
    return shapely.set_precision(shapely.transform(geom, lambda x, y: to_lonlat(x, y), interleaved=False),
                                 1e-6).wkt


@dataclass
class FloodHazard:
    kind = "flood"
    away_tol = A.FLOOD_AWAY_TOLERANCE_M          # meters of rise, not distance
    grid: FloodGrid
    source: str
    rise_m: float
    peak_s: float
    zone: shapely.Geometry                       # land flooded by the peak, metric
    region: shapely.Geometry                     # zone buffered by EXIT_BUFFER_M
    steps: list[tuple[float, float, str]] = field(default_factory=list)   # (t_s, rise_m, wkt lon/lat)

    def _need(self, x, y) -> np.ndarray:
        r, c, ok = self.grid.rc(x, y)
        return np.where(ok, self.grid.rise[self.source][r, c], np.inf)

    @staticmethod
    def _shape(out: np.ndarray, x):
        """Scalar in → scalar out, array in → array out (same as engine.hazard.Hazard)."""
        return out if np.ndim(x) else out[0]

    def need(self, x, y):
        """Meters the lake(s) must rise before water reaches (x, y); inf if it never can."""
        return self._shape(self._need(x, y), x)

    def in_zone(self, x, y):
        return self._shape(self._need(x, y) <= self.rise_m, x)

    def in_region(self, x, y):
        inside = shapely.contains_xy(self.region, np.atleast_1d(np.asarray(x, float)),
                                     np.atleast_1d(np.asarray(y, float)))
        return self._shape(inside | (self._need(x, y) <= self.rise_m), x)

    def arrival_s(self, x, y):
        n = self._need(x, y)
        return self._shape(np.where(n <= self.rise_m, self.peak_s * n / self.rise_m, np.nan), x)

    def distance(self, x, y):
        """Used for 'away' (moving to ground that needs more rise = higher ground)."""
        return self._shape(np.minimum(self._need(x, y), A.FLOOD_DISTANCE_CAP_M), x)

    def geo_distance(self, x, y):
        """Meters from the flooded area (for picking the nearest safe shelter)."""
        pts = shapely.points(np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))
        return self._shape(shapely.distance(self.zone, pts), x)

    def wkt_lonlat(self) -> tuple[str, str]:
        return "", _lonlat_wkt(self.zone)


def elevated_nodes(net) -> set[int]:
    """Intersections that only touch highway classes (bridges / embankments), treated as above the water."""
    G = net.G
    cached = getattr(net, "_elevated_nodes", None)
    if cached is not None:
        return cached
    out = set()
    for n in G.nodes:
        classes = {d["road_class"] for _, _, d in G.out_edges(n, data=True)} | \
                  {d["road_class"] for _, _, d in G.in_edges(n, data=True)}
        if classes and classes <= set(A.FLOOD_ELEVATED_CLASSES):
            out.add(n)
    try:
        net._elevated_nodes = out
    except AttributeError:
        pass
    return out


def build_flood_hazard(net, source: str, rise_m: float, peak_h: float) -> FloodHazard:
    g: FloodGrid | None = getattr(net, "flood", None)
    if g is None:
        raise ValueError("no flood grid: run `python data/flood_dem.py data/silver`")
    if source not in SOURCES:
        raise ValueError(f"unknown flood source {source!r}")
    rise_m = max(float(rise_m), A.FLOOD_MIN_RISE_M)
    peak_s = max(float(peak_h), 0.1) * 3600.0
    need = g.rise[source]
    land = g.lake_code == 0
    zone = _polygonize(g, land & (need <= rise_m))
    region = zone.simplify(20.0).buffer(A.EXIT_BUFFER_M, quad_segs=4) if not zone.is_empty else zone
    shapely.prepare(zone)
    shapely.prepare(region)
    steps = []
    for k in range(1, A.FLOOD_STEPS + 1):
        h = rise_m * k / A.FLOOD_STEPS
        geom = _polygonize(g, land & (need <= h), simplify_m=30.0, factor=2)   # display only: 40 m cells
        steps.append((peak_s * k / A.FLOOD_STEPS, h, _lonlat_wkt(geom)))
    return FloodHazard(grid=g, source=source, rise_m=rise_m, peak_s=peak_s, zone=zone, region=region, steps=steps)
