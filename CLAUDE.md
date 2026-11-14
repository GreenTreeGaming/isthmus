# Isthmus — shared rules

Isthmus is a hazmat evacuation planner for downtown Madison (MadHacks, theme "Let's Dig In").
A train derailment releases a toxic gas; we decide who evacuates vs. shelters in place,
plan departure waves and bus pickups for people who can't leave on their own, and run
hundreds of scenarios on Databricks to find recurring choke points.

## Ownership (one Claude session per area, each in its own git worktree)
- `data/`      — Claude A: ingestion, silver Parquet, Databricks notebooks, batch runs, gold tables
- `engine/`    — Claude B: hazard zone, evacuate-vs-shelter, flow, waves, queue sim, bus routing
- `backend/` + `frontend/` — Claude C: FastAPI + React/deck.gl app
- `contracts/` — owned by a human. Read it before doing anything.

## Rules
- Read every file in `contracts/` before starting work.
- Never edit `contracts/` on your own. If a contract must change, stop and tell the human.
- Only edit files inside your own area.
- Until real data exists, use the fake dataset in `data/fixtures/` (same schema as silver).
- Every tunable assumption (capacities, speeds, compliance, bus fleet) lives in
  `engine/assumptions.py` — one place, imported everywhere.
- Python 3.11+, type hints, pytest for engine logic. Frontend: Vite + React + TypeScript, ESLint.
- Coordinates: WGS84 lon/lat (EPSG:4326) everywhere. Distances in meters, times in seconds,
  speeds in m/s unless a column name says otherwise (e.g. `speed_kph`, `capacity_vph`).
- Commit small and often with clear messages.
- Wording: say "areas with the most residents who need help", never imply we identify individuals.
