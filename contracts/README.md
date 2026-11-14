# Contracts

The agreed interfaces between the three parts. Owned by a human — Claude sessions read, never edit.

| File | Producer | Consumer |
|---|---|---|
| `data_schema.md` | `data/` | `engine/` |
| `engine_api.py` | `engine/` | `backend/`, `data/` (batch runs) |
| `api_response.json` | `backend/` | `frontend/` |

Flow: silver Parquet → `load_network()` + `run_scenario()` → `ScenarioResult` → backend converts to `api_response.json` shape → map.
