"""Request model mirroring contracts/engine_api.py::ScenarioParams (validated at the HTTP edge)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from contracts.engine_api import ScenarioParams


class ScenarioParamsIn(BaseModel):
    release_lon: float = Field(ge=-180, le=180)
    release_lat: float = Field(ge=-90, le=90)
    chemical: Literal["chlorine", "ammonia"] = "chlorine"
    spill_size: Literal["small", "large"] = "large"
    wind_from_deg: float = Field(270.0, ge=0, le=360)
    wind_speed_mps: float = Field(4.0, gt=0, le=40)
    time_of_day: Literal["night", "day", "gameday"] = "day"
    compliance: float = Field(0.85, ge=0, le=1)
    bus_count: int = Field(20, ge=0, le=500)
    bus_capacity: int = Field(60, ge=1, le=200)
    contraflow: bool = False
    closed_edge_ids: list[int] = Field(default_factory=list)
    seed: int = 0

    def to_engine(self) -> ScenarioParams:
        data = self.model_dump()
        data["closed_edge_ids"] = tuple(data["closed_edge_ids"])
        data["wind_from_deg"] = data["wind_from_deg"] % 360
        return ScenarioParams(**data)


def params_to_json(p: ScenarioParams) -> dict:
    """ScenarioParams -> the `params` object of api_response.json (seed omitted, as in the contract)."""
    return {
        "release_lon": p.release_lon,
        "release_lat": p.release_lat,
        "chemical": p.chemical,
        "spill_size": p.spill_size,
        "wind_from_deg": p.wind_from_deg,
        "wind_speed_mps": p.wind_speed_mps,
        "time_of_day": p.time_of_day,
        "compliance": p.compliance,
        "bus_count": p.bus_count,
        "bus_capacity": p.bus_capacity,
        "contraflow": p.contraflow,
        "closed_edge_ids": list(p.closed_edge_ids),
    }
