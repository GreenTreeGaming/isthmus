"""Link-queue traffic simulation (point queues, no spillback).

Each road arc has a free-flow travel time and an outflow capacity per step. Vehicles enter an arc,
become ready to leave after its travel time, then leave at most capacity × step per step (FIFO).
Anything ready but not served waits — that is the queue. Vehicles are fluid amounts, not agents.

Used to (a) check the flow plan, (b) find when each road backs up, (c) drive the map animation,
(d) give buses realistic congested travel times.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from engine import assumptions as A


@dataclass
class Group:
    arcs: list[int]          # road arc indices in order
    vehicles: float
    depart_s: float          # release starts here, spread over release_window_s


@dataclass
class SimResult:
    clearance_s: float               # last vehicle reaches an exit
    peak_ratio: np.ndarray           # per arc: max demand/capacity seen in a step
    congested_at_s: np.ndarray       # per arc: first time demand > capacity (nan if never)
    mean_delay_s: np.ndarray         # per arc: average queue delay in the bus window
    timeline: dict[int, list[float]] # arc -> demand/capacity per step
    step_s: float
    exited: float


def simulate(cap_vph: np.ndarray, tt_s: np.ndarray, groups: list[Group],
             step_s: float | None = None, release_window_s: float | None = None,
             delay_window: tuple[float, float] | None = None, max_s: float | None = None) -> SimResult:
    step_s = step_s or A.SIM_STEP_S
    release_window_s = release_window_s or A.WAVE_INTERVAL_S
    delay_window = delay_window or (A.BUS_DISPATCH_DELAY_S, A.BUS_DISPATCH_DELAY_S + 3600)
    max_s = max_s or A.MAX_SIM_S
    m = len(cap_vph)
    cap_step = cap_vph * step_s / 3600.0
    queues: list[deque] = [deque() for _ in range(m)]
    used_arcs = sorted({a for g in groups for a in g.arcs})

    releases: dict[int, list[tuple[int, float]]] = {}
    n_rel = max(1, int(round(release_window_s / step_s)))
    for gi, g in enumerate(groups):
        if g.vehicles <= 0 or not g.arcs:
            continue
        k0 = int(g.depart_s // step_s)
        for k in range(k0, k0 + n_rel):
            releases.setdefault(k, []).append((gi, g.vehicles / n_rel))
    last_release = max(releases, default=-1)

    def push(a: int, ready: float, gi: int, pos: int, amt: float):
        q = queues[a]
        if q and q[-1][0] == ready and q[-1][2] == gi and q[-1][3] == pos:
            q[-1][1] += amt
        else:
            q.append([ready, amt, gi, pos])

    peak = np.zeros(m)
    congested = np.full(m, np.nan)
    delay_sum = np.zeros(m)
    delay_n = 0
    timeline: dict[int, list[float]] = {a: [] for a in used_arcs}
    exited, clearance = 0.0, 0.0
    in_system = 0.0

    k = 0
    while True:
        t, te = k * step_s, (k + 1) * step_s
        for gi, amt in releases.get(k, ()):
            a0 = groups[gi].arcs[0]
            push(a0, t + tt_s[a0], gi, 0, amt)
            in_system += amt

        in_window = delay_window[0] <= t < delay_window[1]
        if in_window:
            delay_n += 1
        for a in used_arcs:
            q = queues[a]
            if not q:
                timeline[a].append(0.0)
                continue
            c, served = cap_step[a], 0.0
            while q and q[0][0] <= te and served < c - 1e-12:
                item = q[0]
                x = min(item[1], c - served)
                served += x
                item[1] -= x
                gi, pos = item[2], item[3]
                arcs = groups[gi].arcs
                if pos + 1 < len(arcs):
                    nxt = arcs[pos + 1]
                    push(nxt, te + tt_s[nxt], gi, pos + 1, x)
                else:
                    exited += x
                    in_system -= x
                    clearance = te
                if item[1] <= 1e-9:
                    q.popleft()
            waiting = 0.0
            for item in q:
                if item[0] > te:
                    break
                waiting += item[1]
            ratio = (served + waiting) / c if c > 0 else 0.0
            timeline[a].append(round(ratio, 3))
            if ratio > peak[a]:
                peak[a] = ratio
            if ratio > 1.0 and np.isnan(congested[a]):
                congested[a] = t
            if in_window and c > 0:
                delay_sum[a] += waiting / (c / step_s)

        k += 1
        if (k > last_release and in_system <= 1e-6) or k * step_s >= max_s:
            break

    mean_delay = delay_sum / max(delay_n, 1)
    return SimResult(clearance_s=clearance, peak_ratio=peak, congested_at_s=congested,
                     mean_delay_s=mean_delay, timeline=timeline, step_s=step_s, exited=exited)
