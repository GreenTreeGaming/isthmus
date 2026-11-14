# Isthmus

**Hazmat evacuation planner for downtown Madison.** Downtown Madison sits on a narrow isthmus between two
lakes with rail lines running through it. If a train derails and releases a toxic gas, Isthmus decides **who
should evacuate and who should shelter in place**, staggers departures so the few roads out don't gridlock,
routes buses to residents who can't leave on their own **before the gas reaches them**, and runs hundreds of
scenarios on Databricks to find where plans break.

Built at MadHacks (theme: *Let's Dig In*).

## What makes it different

- **Evacuate vs. shelter in place.** For a fast-moving gas, driving out can be more dangerous than staying
  inside. Every block gets a decision based on whether it can beat the gas.
- **People without cars aren't an afterthought.** Census data on households without a car, disability and
  age 65+, plus certified nursing homes, become bus pickups with deadlines.
- **Official hazard zones.** DOT Emergency Response Guidebook 2024 distances, including how they shrink as
  wind speed increases.
- **Real data, checked.** OpenStreetMap roads, 2020 Census, ACS, LEHD LODES daytime population, CMS nursing
  homes. We found and fixed data quirks (e.g. ~22,000 UW–Madison jobs reported on a single campus block).
- **Hundreds of scenarios, not one.** Databricks runs every derailment point × wind direction × wind speed ×
  time of day; the findings hold up when we change our assumptions.

Findings: [`docs/findings.md`](docs/findings.md) · Methods and limitations: [`docs/methods.md`](docs/methods.md)

## Run it

Python 3.12 (3.13+ is too new for OR-Tools) and Node 20+. Clone outside iCloud-synced folders (Desktop,
Documents) — iCloud creates duplicate "file 2" copies.

```bash
git clone https://github.com/GreenTreeGaming/ithumus.git && cd ithumus
uv venv --python 3.12 .venv && source .venv/bin/activate      # or: python3.12 -m venv .venv
uv pip install -r requirements.txt                              # or: pip install -r requirements.txt
cd frontend && npm install && cd ..
```

```bash
# terminal 1 — API with the real engine on the real Madison data (data/silver, committed)
ISTHMUS_ENGINE=real uvicorn backend.main:app --reload --port 8000

# terminal 2 — web app
cd frontend && npm run dev            # http://localhost:5173
```

Click **▶ Demo** for the guided 4-step walkthrough.

```bash
python -m pytest engine/tests backend/tests -q         # 84 tests
python -m engine.run_demo data/silver                  # a few scenarios in the terminal
python -m engine.batch data/silver --out data/gold     # batch → data/gold/insights.json (Planning tab)
python -m engine.robustness data/silver                # assumption variants → data/gold/robustness.json
python data/build_silver_osm.py data/silver            # rebuild data (needs CENSUS_API_KEY in .env)
```

Databricks: add the repo as a Git folder and run
[`data/databricks/batch_scenarios.py`](data/databricks/batch_scenarios.py) on Serverless compute; it writes
`workspace.isthmus.*` Delta tables used by the AI/BI dashboard and the Genie agent.

## Architecture

```
OpenStreetMap · Census 2020 · ACS · LODES · CMS · ERG 2024
        │  data/build_silver_osm.py
        ▼
data/silver/*.parquet  (roads, blocks, facilities, stops, depots, rail, ERG)
        │
        ├──► engine/  run_scenario(): hazard zone → evacuate/shelter → max-flow clearance + min-cost routes
        │            → departure waves → queue simulation → OR-Tools bus routing        (~1 s per scenario)
        │       │
        │       ├──► backend/ (FastAPI /simulate) ──► frontend/ (React + deck.gl + MapLibre)
        │       │
        │       └──► Databricks batch → Delta tables → AI/BI dashboard + Genie agent
        │                    └──► data/gold/insights.json → Planning tab
        │
contracts/  — the agreed interfaces between data, engine and app
```

| Folder | What |
|---|---|
| `contracts/` | Shared data schema, engine API types, example API response |
| `data/` | Data pipeline, silver tables, gold results, Databricks notebook |
| `engine/` | Evacuation engine + tests, batch runner, robustness check |
| `backend/` | FastAPI service |
| `frontend/` | Map app |
| `docs/` | Findings, methods, Devpost draft, demo script |

## Honest limitations

Planning tool, not a plume model; simplified traffic (no spillback, no signals); candidate shelters are not
official designations; assisted living is undercounted. Full list in [`docs/methods.md`](docs/methods.md).
