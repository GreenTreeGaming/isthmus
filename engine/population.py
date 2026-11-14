"""Split each block's population into drivers (vehicles), walkers and people who need a bus."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import assumptions as A

POP_COL = {"night": "pop_night", "day": "pop_day", "gameday": "pop_gameday"}


def split_population(blocks: pd.DataFrame, time_of_day: str) -> pd.DataFrame:
    """Return per-block columns: pop, vehicles, driver_people, walkers, need_bus (before compliance).

    Residents present = min(pop, pop_night); anyone beyond that is a visitor (workers, fans).
    - Car-free residents = residents × zero_vehicle_share.
    - Need a bus = car-free × (disability_share + AGE65_NEED_BUS_WEIGHT × age65_share), capped.
    - Walkers = remaining car-free residents + visitors who didn't drive.
    - Vehicles = car-owning households × VEHICLES_PER_HOUSEHOLD + visitor vehicles.
    """
    b = blocks
    pop = b[POP_COL[time_of_day]].to_numpy(float).clip(min=0)
    night = b["pop_night"].to_numpy(float).clip(min=0)
    zv = b["zero_vehicle_share"].to_numpy(float).clip(0, 1)
    dis = b["disability_share"].to_numpy(float).clip(0, 1)
    old = b["age65_share"].to_numpy(float).clip(0, 1)
    hh = b["households"].to_numpy(float)
    hh_size = np.where(hh > 0, night / np.maximum(hh, 1e-9), A.DEFAULT_HOUSEHOLD_SIZE)
    hh_size = np.clip(hh_size, 1.0, 6.0)

    residents = np.minimum(pop, night)
    visitors = np.maximum(pop - night, 0.0)

    carfree = residents * zv
    need_bus = carfree * np.clip(dis + A.AGE65_NEED_BUS_WEIGHT * old, 0, 1)
    resident_drivers = residents - carfree
    resident_vehicles = resident_drivers / hh_size * A.VEHICLES_PER_HOUSEHOLD

    visitor_drivers = visitors * A.VISITOR_DRIVE_SHARE
    visitor_vehicles = visitor_drivers / A.VISITOR_OCCUPANCY

    return pd.DataFrame({
        "block_id": b["block_id"].to_numpy(),
        "node_id": b["node_id"].to_numpy(),
        "pop": pop,
        "vehicles": resident_vehicles + visitor_vehicles,
        "driver_people": resident_drivers + visitor_drivers,
        "walkers": (carfree - need_bus) + (visitors - visitor_drivers),
        "need_bus": need_bus,
        "age65_share": old,
    })


def facility_need_bus(facilities: pd.DataFrame) -> pd.DataFrame:
    """Nursing-home residents all need assisted transport."""
    if facilities.empty:
        return facilities.assign(need_bus=[])
    nh = facilities[facilities["type"] == "nursing_home"].copy()
    nh["need_bus"] = nh["residents"].astype(float)
    return nh
