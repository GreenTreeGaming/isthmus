# Isthmus — Devpost draft

> Draft for the team to edit. Every number comes from `docs/findings.md`.

**Tagline:** When a train derails in downtown Madison, who should run — and who should stay inside?

## Inspiration

Downtown Madison is an isthmus: a strip of land between two lakes, with rail lines running straight through it
and only a handful of roads out. Evacuation plans usually assume everyone has a car and should leave. We dug
deeper: what if driving out is the more dangerous choice? What about the residents who *can't* drive — people
without cars, people with disabilities, nursing-home residents? And where does traffic actually lock up?

## What it does

Drop a derailment on any rail line, pick the chemical, wind and time of day, and Isthmus produces a plan in
about a second:

- **The official danger zone** from the DOT Emergency Response Guidebook 2024 — including how it shrinks as the
  wind picks up.
- **Evacuate or shelter in place, block by block.** If the gas would reach a block before its residents could
  drive out, they're told to stay inside with windows shut.
- **Departure waves** so the few roads out don't gridlock — highest-risk neighborhoods first.
- **Bus pickups with deadlines** for residents without a car and nursing homes, each scheduled before the gas
  arrives at that stop.
- **A live traffic simulation** showing where and when roads back up.
- A **guided demo**, plain-English "why?" explanations for every block and bus, and a before/after compare mode.

Then we ran **576 scenarios** on Databricks to find what holds across every derailment:

- Capitol Lakes nursing home is inside the danger zone in **75%** of scenarios; Meriter Hospital 62%.
- Madison Metro's bus garage — where every evacuation bus starts — is in the danger zone in **52%**.
- In light wind it takes **105 minutes** on average to get every evacuating car out; in strong wind 40 — but
  strong wind means most people have to shelter instead.
- Traffic jams concentrate on the south-side approaches to the Beltline (Park St / Fish Hatchery Rd), but no
  single road is the choke point in more than ~16% of scenarios — plans have to adapt.
- With 5 buses instead of 20, a light-wind derailment near the Capitol leaves **236 of 536** residents who
  need a ride behind during the day (177 of 477 at night).

## How we built it

- **Data:** OpenStreetMap roads, rail and bus stops (OSMnx); 2020 Census blocks; ACS vehicle, disability and age
  data; LEHD LODES daytime population; CMS nursing homes; ERG 2024 hazard tables; US Census geocoder.
- **Engine (Python):** hazard zone geometry (Shapely), max-flow + binary search for capacity-limited clearance
  time and min-cost flow for routes (OR-Tools graph solvers), capacity-aware departure waves, a link-queue
  traffic simulation, and OR-Tools vehicle routing with time windows for buses. ~1 s per scenario on a
  5,400-intersection network. 84 tests.
- **Databricks:** batch scenario runs in a notebook on Serverless compute → Delta tables → AI/BI dashboard and a
  Genie agent you can ask "which wind direction is worst?"
- **App:** FastAPI backend, React + deck.gl + MapLibre front end.

## Challenges

- **Units.** Road capacity is a rate (cars/hour) but evacuees are a count. We search over time T, give each
  road capacity × T, and find the smallest T that gets everyone out.
- **Fake results from the map edge.** Our first study area made a small street near Olin Park look like the #1
  choke point — it just happened to touch the edge of the map. We expanded the area out to the Beltline.
- **Data quirks.** LODES reports ~22,000 UW–Madison jobs on one campus block; left alone, the model put a
  stadium's worth of cars on one block. We capped daytime density.
- **Speed.** Night scenarios took 5–11 s; we moved bus travel-time computation to compiled shortest paths and
  got it to ~2 s.

## Accomplishments

- Every decision is explainable: click any block or bus to see why.
- Findings survive changing our biggest assumptions (compliance 60–100%, road capacity ±25%, slower warnings).

## What we learned

Warning speed decides who gets to leave: a slower alert doesn't just delay an evacuation — it turns
evacuations into shelter-in-place orders.

## What's next

Real plume modeling instead of ERG zones, official shelter locations, assisted-living facilities, live wind
from the National Weather Service, and multiple bus trips.

## Built with

python · fastapi · networkx · or-tools · shapely · geopandas · osmnx · scipy · react · typescript · deck.gl ·
maplibre · databricks · delta-lake · genie
