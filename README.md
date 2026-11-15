# Isthmus

**When a train derails in downtown Madison, who should run, and who should stay inside?**

Isthmus is a hazmat evacuation planner for downtown Madison, Wisconsin. Drop a derailment on any rail line, pick
the chemical, wind and time of day, and in about a second it decides **who evacuates and who shelters in
place**, staggers departures so the few roads out don't gridlock, and routes buses to residents who can't leave
on their own, **before the gas reaches them**. Then it runs hundreds of scenarios on Databricks to find where
plans break.

Built at **MadHacks** for the theme *Let's Dig In*.

<!-- Add a screenshot of the ▶ Demo map here: ![Isthmus map](docs/screenshot.png) -->

## Why Madison

Downtown Madison sits on a strip of land between Lake Mendota and Lake Monona. Rail lines run straight through
it, and only a handful of roads lead out. Standard evacuation plans assume everyone has a car and should
leave. For a fast-moving toxic gas, driving out can be the more dangerous choice, and residents without a car
are often an afterthought.

## What we found (576 scenarios on Databricks)

| Finding | Number |
|---|---|
| Capitol Lakes nursing home is inside the danger zone | **75%** of scenarios |
| Madison Metro's bus garage, where every evacuation bus starts, is inside it | **52%** |
| Time until the last car is out: light wind vs. strong wind | **105 min** vs. **40 min** |
| Most often the worst traffic jam (Latitude 43 St, south-side Beltline approaches) | only **~16%**, so no fixed plan works |
| 5 buses instead of 20, light-wind derailment near the Capitol (daytime) | **236 of 536** people who need a ride are left behind |

Wind from the south is the worst direction (78 min vs. 56 min from the southeast), and game day is the slowest
time of day. The findings hold when we change our biggest assumptions. Full details:
[`docs/findings.md`](docs/findings.md).

## Features

- **Official danger zones.** Isolation circle and downwind protective-action area from the DOT Emergency
  Response Guidebook (ERG) 2024, rail tank car values, scaled by wind speed band.
- **Evacuate or shelter, block by block.** A block evacuates only if its residents can drive out before the gas
  arrives; otherwise they're told to stay inside.
- **Departure waves.** Highest-risk neighborhoods leave first, and each wave fits within road capacity.
- **Bus pickups with deadlines.** Residents without a car, people with disabilities, seniors and nursing-home
  residents get pickups, each scheduled before the gas reaches that stop.
- **Live traffic simulation.** Watch where and when roads back up.
- **Explainable.** Click any block or bus to see *why* it got its decision. There is also a before/after compare
  mode and a guided 4-step **▶ Demo**.
- **Planning tab.** Results from the 576-scenario batch: facility exposure, choke points, and wind and time
  breakdowns.
- **Every assumption visible.** All tunables are shown in the app's Assumptions tab.

## How it works

```
OpenStreetMap · Census 2020 · ACS · LODES · CMS · ERG 2024
        │  data/build_silver_osm.py
        ▼
data/silver/*.parquet   5,441 intersections · 13,909 road segments · 2,113 Census blocks · ~200k people
        │
        ├──► engine/  run_scenario()                                   (~1 s per scenario)
        │      1. hazard zone (ERG 2024)          5. departure waves
        │      2. away-only road rules            6. link-queue traffic simulation
        │      3. evacuate vs. shelter            7. OR-Tools bus routing with time windows
        │      4. max-flow clearance time + min-cost routes
        │       │
        │       ├──► backend/  FastAPI /simulate ──► frontend/  React + deck.gl + MapLibre
        │       │
        │       └──► Databricks batch → Delta tables → AI/BI dashboard + Genie agent
        │                    └──► data/gold/insights.json → Planning tab
        │
contracts/  agreed interfaces between data, engine and app
```

The core technical step: road capacity is a **rate** (cars/hour) but evacuees are a **count**. For a candidate
duration T, each road can carry capacity × T cars. A binary search finds the smallest T where max-flow gets
every car out. The min cut gives the binding bottlenecks, and min-cost flow assigns the actual routes. Full
pipeline, assumptions and limitations: [`docs/methods.md`](docs/methods.md).

## Tech stack

| Layer | Tools |
|---|---|
| Data | OSMnx, GeoPandas, Shapely 2, pyproj, Census / ACS / LODES / CMS APIs |
| Engine | OR-Tools (max-flow, min-cost flow, vehicle routing), NetworkX, SciPy sparse shortest paths, NumPy |
| Batch | Databricks Serverless notebook, Delta Lake, AI/BI dashboard, Genie |
| Backend | FastAPI, Uvicorn |
| Frontend | React 19, TypeScript, Vite, deck.gl, MapLibre, Recharts |

## Getting started

### Prerequisites

- **Python 3.12** (3.13+ is too new for OR-Tools)
- **Node 20+**
- Clone outside iCloud-synced folders (Desktop, Documents); iCloud creates duplicate "file 2" copies.

### Install

```bash
git clone https://github.com/GreenTreeGaming/ithumus.git && cd ithumus
uv venv --python 3.12 .venv && source .venv/bin/activate     # or: python3.12 -m venv .venv
uv pip install -r requirements.txt                             # or: pip install -r requirements.txt
cd frontend && npm install && cd ..
```

The processed Madison data (`data/silver/`) and batch results (`data/gold/`) are committed, so no API keys
are needed to run the app.

### Run

```bash
# terminal 1: API using the real engine on real Madison data
ISTHMUS_ENGINE=real uvicorn backend.main:app --reload --port 8000

# terminal 2: web app
cd frontend && npm run dev            # http://localhost:5173
```

Open http://localhost:5173 and click **▶ Demo** for the guided walkthrough. Or click the map near a rail line to place a
derailment and adjust chemical, spill size, wind, time of day, compliance, bus count and contraflow.

`ISTHMUS_ENGINE` can also be `mock` (fast synthetic results that react to every input) or `placeholder` (the
example response in `contracts/`), so you can work on the frontend without the engine.

## Usage from the command line

```bash
python -m engine.run_demo data/silver                       # run a few scenarios, print summaries
python -m engine.batch data/silver --n-points 8 --out data/gold   # 576-scenario batch → data/gold/insights.json
python -m engine.robustness data/silver                     # 7 assumption variants → data/gold/robustness.json
python data/build_silver_osm.py data/silver                 # rebuild data (needs CENSUS_API_KEY in .env)
```

## API

| Method | Endpoint | Returns |
|---|---|---|
| `POST` | `/simulate` | Full plan for one scenario: zone, block decisions, road loads, bus routes, summary, timeline |
| `GET` | `/insights` | 576-scenario batch findings (Planning tab) |
| `GET` | `/block-frequency` | How often each block is in the danger zone |
| `GET` | `/rail` | Rail lines for placing a derailment |
| `GET` | `/blocks` | Census blocks |
| `GET` | `/assumptions` | Every tunable number in the engine |
| `GET` | `/health` | Status and engine mode |

Request and response shapes are in [`contracts/`](contracts/) (`engine_api.py`, `api_response.json`).

## Databricks

1. Add this repo as a **Git folder** in your workspace.
2. Open [`data/databricks/batch_scenarios.py`](data/databricks/batch_scenarios.py) on **Serverless** compute and
   click **Run all**.
3. It writes `workspace.isthmus.*` Delta tables (`scenario_results` plus `gold_*` summaries). These feed the
   AI/BI dashboard and a Genie agent you can ask questions like *"Which wind direction gives the longest
   clearance time?"*

## Testing

```bash
python -m pytest engine/tests backend/tests -q     # 84 tests
cd frontend && npm run build && npm run lint
```

The tests cover units (rate × time vs. count), road rules, waves staying within capacity, bus deadlines never
being violated, agreement between fast and fallback routing, and API responses.

## Data sources

All public: OpenStreetMap (roads, rail, bus stops, hospitals), 2020 Census blocks, ACS 2022 5-year (no-vehicle
households, age 65+, disability), LEHD LODES 2022 (daytime population), CMS nursing homes, DOT ERG 2024 via
NOAA CAMEO Chemicals, and the US Census geocoder.

We dug into the data, too. LODES puts about **22,000 UW–Madison jobs on a single campus block**, which would
have put a stadium's worth of cars on one city block. We cap daytime density at 100,000 people/km².

## Limitations

Isthmus is a **planning tool, not a plume model**. Zones follow ERG guidance, and gas arrival is distance ÷ wind
speed. Traffic is a simplified queue model (no spillback or signals), so it's good for ranking and orders of
magnitude, not exact minutes. The candidate shelters are large public buildings, **not official city
designations**. Assisted-living facilities are undercounted, and students are missing from daytime jobs data.
Population is estimated by area, never by individual. Full list in [`docs/methods.md`](docs/methods.md).

## Project structure

| Folder | What |
|---|---|
| `contracts/` | Shared data schema, engine API types, example API response |
| `data/` | Data pipeline, silver tables, gold results, Databricks notebook |
| `engine/` | Evacuation engine, tests, batch runner, robustness check |
| `backend/` | FastAPI service |
| `frontend/` | Map app |
| `docs/` | [Findings](docs/findings.md), [methods](docs/methods.md), [Devpost draft](docs/devpost.md), [demo script](docs/demo-script.md) |

## Roadmap

Real plume modeling, official shelter locations, assisted-living facilities, live wind from the National Weather
Service, and buses making multiple trips.
