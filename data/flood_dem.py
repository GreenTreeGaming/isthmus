"""Flood grid for the lake-flood hazard: how far each lake must rise before water can reach every 20 m cell.

    python data/flood_dem.py data/silver          # writes data/silver/flood_grid.npz

1. Elevation: USGS 3DEP (1/3 arc-second, lidar-derived) from the National Map ImageServer, ~10 m, in UTM 16N,
   averaged to 20 m. Downloaded once into cache/dem/.
2. Lakes: lidar DEMs "hydro-flatten" water to one constant height, so each lake is a large perfectly flat area.
   We pick the flat areas under known points in Lake Mendota and Lake Monona (plus the Yahara River and Upper
   Mud Lake below Monona, which sit at Monona's level). Mendota was flown in two lidar collections and is
   flattened at two heights (258.96 m and 257.99 m) — so a lake is identified by its shape, and its *normal
   level* is the flattened height at the main seed point (Mendota 258.96 m ≈ 849.6 ft, its normal summer
   level; Monona 257.00 m).
3. Priority-flood (Barnes et al. 2014, 4-neighbour): starting from the lake, the lowest water level at which
   each cell is connected to the lake — water has to flow there; it can't jump over higher ground. The other
   lake is a barrier (the Tenney dam holds Mendota ~2 m above Monona; a rising lake drains into a lower one).
   rise_needed = that level − the lake's normal level. Land below the normal level that connects to the lake
   (≈0.3 km², shoreline lidar noise) floods at the first centimeters of rise.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import requests
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.flood import priority_flood  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "dem"
BBOX = (-89.47, 43.015, -89.29, 43.125)        # same study area as build_silver_osm.py
SIZE = (1500, 1250)                            # ~10 m pixels for this bbox
SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
FLAT_TOL_M = 0.005
MIN_LAKE_CELLS = 3000                          # at 10 m: 0.3 km²

# Points inside each lake's flattened water surface (lon, lat). The first point sets the normal level.
LAKE_SEEDS = {
    "mendota": [(-89.42, 43.105), (-89.4004, 43.0857)],                    # two lidar collections
    "monona": [(-89.365, 43.065), (-89.3184, 43.0225), (-89.3165, 43.0385)],  # Monona, Yahara south, Upper Mud
}
LAKE_CODE = {"mendota": 1, "monona": 2}


def read_tiff_f32(data: bytes) -> np.ndarray:
    """Minimal reader for the uncompressed, single-band float32 (tiled or stripped) TIFF the service returns."""
    if data[:2] != b"II":
        raise ValueError("expected little-endian TIFF")
    off = struct.unpack("<I", data[4:8])[0]
    n = struct.unpack("<H", data[off:off + 2])[0]
    tags = {}
    for i in range(n):
        tag, typ, cnt, val = struct.unpack("<HHII", data[off + 2 + 12 * i: off + 14 + 12 * i])
        tags[tag] = (typ, cnt, val)

    def ints(tag):
        typ, cnt, val = tags[tag]
        size = 2 if typ == 3 else 4
        if cnt * size <= 4:
            return list(struct.unpack("<" + ("H" if typ == 3 else "I") * cnt,
                                      struct.pack("<I", val)[: cnt * size]))
        return np.frombuffer(data[val: val + cnt * size], "<u2" if typ == 3 else "<u4").tolist()

    W, H = ints(256)[0], ints(257)[0]
    if ints(258)[0] != 32 or ints(259)[0] != 1:
        raise ValueError("expected uncompressed 32-bit samples")
    if 322 in tags:                                         # tiled
        tw, th = ints(322)[0], ints(323)[0]
        nx = -(-W // tw)
        out = np.zeros((-(-H // th) * th, nx * tw), "f4")
        for k, o in enumerate(ints(324)):
            r, c = divmod(k, nx)
            out[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = np.frombuffer(data[o:o + tw * th * 4], "<f4").reshape(th, tw)
        return out[:H, :W]
    rps = ints(278)[0] if 278 in tags else H                # stripped
    rows = [np.frombuffer(data[o:o + bc], "<f4") for o, bc in zip(ints(273), ints(279))]
    return np.concatenate(rows)[: W * H].reshape(H, W) if rps else np.zeros((H, W), "f4")


def fetch_dem() -> tuple[np.ndarray, float, float, float]:
    """(elevation m [rows top→bottom], x0, y_top, cell_m) in UTM 16N, cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    tif, meta = CACHE / "dem.tif", CACHE / "dem_extent.txt"
    common = dict(bbox=",".join(map(str, BBOX)), bboxSR=4326, imageSR=32616, size=f"{SIZE[0]},{SIZE[1]}",
                  format="tiff", pixelType="F32", interpolation="RSP_BilinearInterpolation")
    if not (tif.exists() and meta.exists()):
        ext = requests.get(SERVICE, params={**common, "f": "json"}, timeout=120).json()["extent"]
        r = requests.get(SERVICE, params={**common, "f": "image"}, timeout=300)
        r.raise_for_status()
        tif.write_bytes(r.content)
        meta.write_text(f"{ext['xmin']} {ext['ymin']} {ext['xmax']} {ext['ymax']}")
    xmin, ymin, xmax, ymax = map(float, meta.read_text().split())
    a = read_tiff_f32(tif.read_bytes())
    return a, xmin, ymax, (xmax - xmin) / a.shape[1]


def lake_masks(a: np.ndarray, x0: float, y_top: float, cell: float) -> dict[str, tuple[np.ndarray, float]]:
    """{lake: (mask, normal_level_m)} from flattened water around the seed points."""
    import pyproj
    t = pyproj.Transformer.from_crs(4326, 32616, always_xy=True)
    out = {}
    for lake, seeds in LAKE_SEEDS.items():
        mask = np.zeros(a.shape, bool)
        level = None
        for lon, lat in seeds:
            x, y = t.transform(lon, lat)
            r, c = int((y_top - y) / cell), int((x - x0) / cell)
            v = float(a[r, c])
            lab, _ = ndimage.label(np.abs(a - v) < FLAT_TOL_M)
            comp = lab == lab[r, c]
            if lab[r, c] == 0 or comp.sum() < MIN_LAKE_CELLS:
                raise ValueError(f"{lake} seed {lon},{lat} is not on flat water (got {v:.2f} m)")
            mask |= comp
            level = v if level is None else level
        out[lake] = (mask, level)
    return out


def build(out_dir: str | Path) -> Path:
    a, x0, y_top, cell = fetch_dem()
    lakes = lake_masks(a, x0, y_top, cell)
    # 2×2 average → ~20 m cells
    H2, W2 = a.shape[0] // 2, a.shape[1] // 2

    def down(x, f):
        return f(x[: H2 * 2, : W2 * 2].reshape(H2, 2, W2, 2), axis=(1, 3))

    elev = down(a, np.mean)
    masks = {k: down(m, np.any) for k, (m, _) in lakes.items()}
    masks["monona"] &= ~masks["mendota"]
    lake_code = np.zeros(elev.shape, np.int8)
    for k, m in masks.items():
        lake_code[m] = LAKE_CODE[k]
    out = {"x0": x0, "y_top": y_top, "cell": cell * 2, "lake_code": lake_code}
    for k, (_, level) in lakes.items():
        other = (lake_code != 0) & (lake_code != LAKE_CODE[k])
        rise = priority_flood(elev, masks[k], other) - level
        out[f"rise_{k}"] = rise.astype(np.float32)
        out[f"level_{k}"] = level
        land = lake_code == 0
        print(f"{k}: normal level {level:.2f} m; land flooded at +1 m: "
              f"{(land & (rise <= 1)).sum() * (cell * 2) ** 2 / 1e6:.1f} km²")
    path = Path(out_dir) / "flood_grid.npz"
    np.savez_compressed(path, **out)
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB, {elev.shape[1]}×{elev.shape[0]} cells of {cell * 2:.1f} m)")
    return path


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "silver")
