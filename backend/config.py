"""Backend settings. Everything switchable lives here.

ENGINE_MODE picks where /simulate results come from:
  - "placeholder": contracts/api_response.json, verbatim (params echoed back)
  - "mock":        synthetic scenario in the same shape that reacts to every input (demo / UI testing)
  - "real":        engine.run_scenario + backend/convert.py

To switch to the real engine, change the default below (or set ISTHMUS_ENGINE=real).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

EngineMode = Literal["placeholder", "mock", "real"]

ENGINE_MODE: EngineMode = os.environ.get("ISTHMUS_ENGINE", "placeholder")  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_RESPONSE = REPO_ROOT / "contracts" / "api_response.json"
PLACEHOLDER_DIR = Path(__file__).resolve().parent / "placeholder"
GOLD_DIR = REPO_ROOT / "data" / "gold"


def silver_dir() -> Path:
    """Real silver tables if present, otherwise the committed fixtures (same schema)."""
    override = os.environ.get("ISTHMUS_DATA_DIR")
    if override:
        return Path(override)
    silver = REPO_ROOT / "data" / "silver"
    return silver if silver.exists() else REPO_ROOT / "data" / "fixtures"


CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
