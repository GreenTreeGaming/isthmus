"""Synthetic scenario generator — same shape as contracts/api_response.json.

NOT the engine. It exists so the UI can be exercised end-to-end (every control changes
the map) before engine/ is ready. Numbers are illustrative only. Enable with ISTHMUS_ENGINE=mock.
"""
from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from shapely.geometry import Point, Polygon

from contracts.engine_api import ScenarioParams
from backend.schemas import params_to_json

LON0, LAT0 = -89.38, 43.075
M_PER_DEG_LON = 111_320 * math.cos(math.radians(LAT0))
M_PER_DEG_LAT = 110_540

# Rough land mask for the isthmus + campus + south side (mock only).
LAND = Polygon([
    (-89.418, 43.0760), (-89.405, 43.0772), (-89.395, 43.0790), (-89.385, 43.0808),
    (-89.375, 43.0860), (-89.365, 43.0912), (-89.355, 43.0966), (-89.345, 43.1012),
    (-89.335, 43.1062), (-89.325, 43.1120), (-89.318, 43.1120), (-89.318, 43.0930),
    (-89.330, 43.0905), (-89.340, 43.0878), (-89.350, 43.0843), (-89.362, 43.0790),
    (-89.372, 43.0744), (-89.380, 43.0704), (-89.386, 43.0688), (-89.392, 43.0664),
    (-89.395, 43.0600), (-89.418, 43.0600),
])

ROADS: list[tuple[str, int, list[tuple[float, float]]]] = [
    ("E Washington Ave", 3, [(-89.3829, 43.0759), (-89.3720, 43.0815), (-89.3600, 43.0880), (-89.3450, 43.0960), (-89.3300, 43.1040), (-89.3190, 43.1100)]),
    ("E Johnson St", 2, [(-89.3860, 43.0790), (-89.3750, 43.0845), (-89.3620, 43.0915), (-89.3500, 43.0980)]),
    ("E Gorham St", 2, [(-89.3855, 43.0782), (-89.3760, 43.0832), (-89.3650, 43.0890)]),
    ("Williamson St", 1, [(-89.3770, 43.0745), (-89.3650, 43.0805), (-89.3520, 43.0868), (-89.3420, 43.0905)]),
    ("John Nolen Dr", 2, [(-89.3790, 43.0705), (-89.3700, 43.0620), (-89.3620, 43.0550)]),
    ("W Washington Ave", 2, [(-89.3860, 43.0730), (-89.3960, 43.0680), (-89.4050, 43.0640)]),
    ("University Ave", 3, [(-89.3890, 43.0745), (-89.4000, 43.0730), (-89.4170, 43.0725)]),
    ("Park St", 2, [(-89.4005, 43.0750), (-89.4010, 43.0650), (-89.4010, 43.0560)]),
    ("Blair St", 2, [(-89.3745, 43.0810), (-89.3725, 43.0770), (-89.3790, 43.0708)]),
    ("N First St", 2, [(-89.3565, 43.0905), (-89.3550, 43.1000), (-89.3540, 43.1080)]),
    ("Fordem Ave", 1, [(-89.3660, 43.0890), (-89.3700, 43.0960), (-89.3720, 43.1040)]),
    ("Milwaukee St", 1, [(-89.3400, 43.0910), (-89.3280, 43.0950), (-89.3180, 43.0980)]),
]
LANE_VPH = 1800

GARAGE = ("garage_metro", (-89.3700, 43.0835))
SHELTERS = [("shelter_alliant", (-89.3760, 43.0500)), ("shelter_truax", (-89.3290, 43.1240)),
            ("shelter_westcampus", (-89.4180, 43.0740))]

# Mock-only hazard distances (m). The engine uses data/ erg_distances instead.
ERG = {("chlorine", "small"): (60, 400, 1600), ("chlorine", "large"): (500, 2400, 5200),
       ("ammonia", "small"): (30, 100, 200), ("ammonia", "large"): (150, 800, 2000)}


def _xy(lon: float, lat: float) -> tuple[float, float]:
    return (lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT


def _ll(x: float, y: float) -> list[float]:
    return [round(LON0 + x / M_PER_DEG_LON, 6), round(LAT0 + y / M_PER_DEG_LAT, 6)]


def _h(*parts: object) -> float:
    """Deterministic 0..1 hash so block attributes are stable between runs."""
    d = hashlib.md5("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(d[:4], "little") / 2**32


def blocks_geojson() -> dict[str, Any]:
    """Static block outlines for GET /blocks (ids match run_mock's `blocks` keys)."""
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"block_id": b["id"]}, "geometry": {"type": "Polygon", "coordinates": [b["ring"]]}}
        for b in _blocks("day")]}


def _blocks(time_of_day: str) -> list[dict[str, Any]]:
    out = []
    cell = 0.0026  # ~210 m
    lon = -89.418
    i = 0
    while lon < -89.318:
        lat = 43.060
        while lat < 43.112:
            c = Point(lon + cell / 2, lat + cell * 0.38)
            if LAND.contains(c):
                x, y = _xy(c.x, c.y)
                dc = math.hypot(x - _xy(-89.3841, 43.0747)[0], y - _xy(-89.3841, 43.0747)[1])
                night = 120 + 520 * math.exp(-dc / 1400) + 260 * _h("p", i)
                day = night * (1.0 + 1.6 * math.exp(-dc / 900))
                d_stadium = math.hypot(*(a - b for a, b in zip((x, y), _xy(-89.4127, 43.0700))))
                game = day + 9000 * math.exp(-d_stadium / 350)
                pop = {"night": night, "day": day, "gameday": game}[time_of_day]
                east = max(0.0, (c.x + 89.37) / 0.05)
                zv = min(0.6, 0.06 + 0.22 * east + 0.18 * _h("z", i) ** 2)
                dis = min(0.4, 0.06 + 0.12 * _h("d", i) + 0.06 * east)
                a65 = min(0.5, 0.05 + 0.2 * _h("a", i) ** 3)
                ring = [[lon, lat], [lon + cell, lat], [lon + cell, lat + cell * 0.76], [lon, lat + cell * 0.76], [lon, lat]]
                out.append({"id": f"5502500{i:08d}", "x": x, "y": y, "ring": ring, "pop": pop,
                            "zv": zv, "dis": dis, "a65": a65})
                i += 1
            lat += cell * 0.76
        lon += cell
    return out


def _densify(pts: list[tuple[float, float]], step_m: float = 220) -> list[list[tuple[float, float]]]:
    segs = []
    for (a, b) in zip(pts, pts[1:]):
        ax, ay = _xy(*a)
        bx, by = _xy(*b)
        n = max(1, round(math.hypot(bx - ax, by - ay) / step_m))
        for k in range(n):
            segs.append([(ax + (bx - ax) * k / n, ay + (by - ay) * k / n),
                         (ax + (bx - ax) * (k + 1) / n, ay + (by - ay) * (k + 1) / n)])
    return segs


def run_mock(p: ScenarioParams) -> dict[str, Any]:
    t0 = time.perf_counter()
    iso, prot_day, prot_night = ERG[(p.chemical, p.spill_size)]
    L = prot_night if p.time_of_day == "night" else prot_day
    rx, ry = _xy(p.release_lon, p.release_lat)
    bearing = math.radians((p.wind_from_deg + 180) % 360)
    ux, uy = math.sin(bearing), math.cos(bearing)        # downwind unit vector
    vx, vy = -uy, ux                                      # crosswind
    w = max(0.5, p.wind_speed_mps)

    def half_width(along: float) -> float:
        return iso + (L / 2 - iso) * min(1.0, along / L)

    circle = [_ll(rx + iso * math.cos(a), ry + iso * math.sin(a))
              for a in (2 * math.pi * k / 64 for k in range(65))]
    cone_r = [_ll(rx + ux * a + vx * half_width(a), ry + uy * a + vy * half_width(a)) for a in (0, L * 0.5, L)]
    cone_l = [_ll(rx + ux * a - vx * half_width(a), ry + uy * a - vy * half_width(a)) for a in (L, L * 0.5, 0)]
    zones = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"kind": "isolation"}, "geometry": {"type": "Polygon", "coordinates": [circle]}},
        {"type": "Feature", "properties": {"kind": "protect"},
         "geometry": {"type": "Polygon", "coordinates": [cone_r + cone_l + [cone_r[0]]]}},
    ]}

    speedup = 0.8 if p.contraflow else 1.0
    blocks_out: dict[str, dict[str, Any]] = {}
    evac_pts = []
    max_wave = 0
    evac_people = shelter_people = need_bus_total = 0.0
    bus_demand: list[tuple[float, str, float, float, float]] = []
    for b in _blocks(p.time_of_day):
        dx, dy = b["x"] - rx, b["y"] - ry
        d = math.hypot(dx, dy)
        along, cross = dx * ux + dy * uy, dx * vx + dy * vy
        in_iso = d <= iso + 160  # ~half a cell: count blocks the circle touches
        in_prot = -110 <= along <= L and abs(cross) <= half_width(max(along, 0)) + 110
        vuln = min(1.0, 0.45 * b["zv"] + 0.35 * b["dis"] + 0.2 * b["a65"]) / 0.42
        need_bus = b["pop"] * (0.35 * b["zv"] + 0.25 * b["dis"])
        props: dict[str, Any] = {"block_id": b["id"], "plume_arrival_s": None, "est_exit_time_s": None,
                                 "wave": None, "drivers": 0, "walkers": 0, "need_bus": 0,
                                 "vulnerability": round(min(1.0, vuln), 3)}
        if in_iso or in_prot:
            arrival = 120 + max(0.0, along if in_prot else d) / (0.45 * w)  # dispersion slows the front
            dist_out = min(half_width(max(along, 0)) - abs(cross), L - along) if in_prot else iso - d
            exit_t = (300 + 240 * vuln + max(0.0, dist_out) / 5.0) * speedup
            evacuate = in_iso and arrival > 180 or exit_t < arrival * 0.9
            props.update(plume_arrival_s=round(arrival), est_exit_time_s=round(exit_t),
                         need_bus=round(need_bus))
            if evacuate:
                need_bus_total += need_bus
                leaving = b["pop"] * p.compliance
                walk = leaving * 0.12
                props.update(decision="evacuate", wave=min(3, int(arrival // 900)),
                             drivers=round((leaving - walk - need_bus) / 1.6 if leaving > walk + need_bus else 0),
                             walkers=round(walk))
                evac_people += leaving
                evac_pts.append((b["x"], b["y"], props["drivers"], arrival))
                bus_demand.append((arrival, b["id"], b["x"], b["y"], need_bus))
            else:
                props["decision"] = "shelter"
                shelter_people += b["pop"]
        else:
            props["decision"] = "outside"
        if props.get("wave") is not None:
            max_wave = max(max_wave, props["wave"])
        blocks_out[props.pop("block_id")] = props

    # ---- roads
    total_veh = sum(e[2] for e in evac_pts)
    exit_lanes = 12 * (1.5 if p.contraflow else 1.0)
    clearance = 900 + total_veh / (exit_lanes * LANE_VPH / 3600) if total_veh else 0.0
    step = 30
    n_steps = max(2, int(clearance / step) + 20) if clearance else 2
    closed = set(p.closed_edge_ids)
    edges, timeline = [], {}
    for ri, (name, lanes, pts) in enumerate(ROADS):
        cap = lanes * LANE_VPH * (1.5 if p.contraflow else 1.0)
        for si, ((ax, ay), (bx, by)) in enumerate(_densify(pts)):
            eid = 1000 + ri * 100 + si
            if eid in closed:
                continue
            mx, my = (ax + bx) / 2, (ay + by) / 2
            flow = sum(v * math.exp(-math.hypot(mx - x, my - y) / 450) for x, y, v, _ in evac_pts) * 0.55
            if flow < 5:
                continue
            hours = 0.55  # peak-hour window
            ratio = flow / (cap * hours) * (0.9 + 0.3 * _h("e", eid))
            tp = 600 + 0.55 * clearance * min(1.0, math.hypot(mx - rx, my - ry) / max(L, 1))
            series = [round(ratio * (t / tp) ** 2 * math.exp(2 * (1 - t / tp)), 3) if t > 0 else 0.0
                      for t in (k * step for k in range(n_steps))]
            congested = next((k * step for k, v in enumerate(series) if v >= 1.0), None)
            edges.append({"type": "Feature",
                          "geometry": {"type": "LineString", "coordinates": [_ll(ax, ay), _ll(bx, by)]},
                          "properties": {"edge_id": eid, "name": name, "flow_veh": round(flow),
                                         "peak_load_ratio": round(ratio, 3), "congested_at_s": congested,
                                         "is_bottleneck": False}})
            timeline[str(eid)] = series
    ranked = sorted(edges, key=lambda f: -f["properties"]["peak_load_ratio"])
    bottlenecks = [f["properties"]["edge_id"] for f in ranked[:4] if f["properties"]["peak_load_ratio"] > 0.9]
    for f in ranked[:4]:
        if f["properties"]["edge_id"] in bottlenecks:
            f["properties"]["is_bottleneck"] = True

    # ---- buses: one trip each, greedy by plume arrival
    def dist_ll(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(*(i - j for i, j in zip(_xy(*a), _xy(*b))))

    def in_plume(ll: tuple[float, float]) -> bool:
        x, y = _xy(*ll)
        al = (x - rx) * ux + (y - ry) * uy
        return math.hypot(x - rx, y - ry) < iso or (0 <= al <= L and abs((x - rx) * vx + (y - ry) * vy) <= half_width(al))

    safe = [s for s in SHELTERS if not in_plume(s[1])] or SHELTERS
    shelter = max(safe, key=lambda s: dist_ll(s[1], (p.release_lon, p.release_lat)))
    bus_speed = 7.0
    queue = sorted([[a, bid, x, y, n] for a, bid, x, y, n in bus_demand if n >= 1])
    buses, served = [], 0.0
    for bus_id in range(p.bus_count):
        if not queue:
            break
        stops, arr, load, path, dl = [GARAGE[0]], [0.0], [0], [list(GARAGE[1])], [None]
        t, pos, onboard = 0.0, GARAGE[1], 0
        while queue and len(stops) < 4 and onboard < p.bus_capacity:
            j = 0
            if len(stops) > 1:  # after the most urgent pickup, chain the nearest nearby ones
                j = min(range(min(12, len(queue))), key=lambda k: dist_ll(pos, tuple(_ll(queue[k][2], queue[k][3]))))
                if dist_ll(pos, tuple(_ll(queue[j][2], queue[j][3]))) > 700:
                    break
            a, bid, x, y, n = queue[j]
            ll = tuple(_ll(x, y))
            t_next = t + dist_ll(pos, ll) / bus_speed + 90
            if t_next > a:  # like the engine: never schedule a pickup after the gas arrives
                queue.pop(j)
                continue
            t = t_next
            take = min(n, p.bus_capacity - onboard)
            served += take
            onboard += int(round(take))
            queue[j][4] -= take
            if queue[j][4] < 1:
                queue.pop(j)
            stops.append(f"stop_{bid[-5:]}")
            arr.append(round(t))
            load.append(onboard)
            path.append(list(ll))
            dl.append(round(a))
            pos = ll
        t += dist_ll(pos, shelter[1]) / bus_speed
        stops.append(shelter[0])
        arr.append(round(t))
        load.append(0)
        path.append(list(shelter[1]))
        dl.append(None)
        if len(stops) == 2:  # nobody reachable in time
            continue
        buses.append({"bus_id": bus_id, "stops": stops, "arrival_s": arr, "load": load, "path": path, "deadline_s": dl,
                      "stop_coords": [list(c) for c in path]})

    return {
        "params": params_to_json(p),
        "summary": {
            "clearance_time_s": round(clearance),
            "people_evacuating": round(evac_people),
            "people_sheltering": round(shelter_people),
            "need_bus_total": round(need_bus_total),
            "need_bus_unserved": round(max(0.0, need_bus_total - served)),
            "bottleneck_edge_ids": bottlenecks,
            "runtime_ms": round((time.perf_counter() - t0) * 1000),
            # alert -> last car out: mobilization + wave stagger + driving
            "sim_clearance_s": round(300 + max_wave * 600 + clearance) if clearance else 0,
        },
        "zones": zones,
        "blocks": blocks_out,
        "edges": {"type": "FeatureCollection", "features": edges},
        "buses": buses,
        "timeline": {"step_s": step, "edge_load": timeline},
    }
