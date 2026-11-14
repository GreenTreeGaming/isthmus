# Isthmus backend (FastAPI)

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload --port 8000      # run from the repo root
.venv/bin/python -m pytest backend -q
```

## Engine mode (`backend/config.py` → `ENGINE_MODE`, or env `ISTHMUS_ENGINE`)
| mode | `/simulate` returns |
|---|---|
| `placeholder` (default) | `contracts/api_response.json` verbatim, with your params echoed |
| `mock` | synthetic scenario in the same shape that reacts to every control (UI demo / testing only) |
| `real` | `engine.run_scenario(params, network)` → `backend/convert.py` → contract shape |

Switching to the real engine is one line: set `ENGINE_MODE` default to `"real"` (or `ISTHMUS_ENGINE=real`).
In `real` mode the engine network and silver lookup tables (`data/silver/`, falling back to `data/fixtures/`)
load once at startup.

## Endpoints
- `POST /simulate` — body = `ScenarioParams` as JSON (see `contracts/engine_api.py`). Response = `contracts/api_response.json` shape.
- `GET /insights` — merged `data/gold/*.json` (key = file stem); `backend/placeholder/insights.json` until gold exists.
- `GET /rail` — `rail_lines` as GeoJSON; `backend/placeholder/rail.geojson` (hand-traced, approximate) until silver exists.
- `GET /health`

Every response carries `X-Isthmus-Source` (placeholder / mock / real / gold) so the UI can label its data.
