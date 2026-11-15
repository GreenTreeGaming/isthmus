# Methods, assumptions and limitations

Isthmus is a **planning tool**, not a dispersion model. It answers: *if a train derails and releases a toxic
gas near downtown Madison, who should evacuate, who should shelter in place, in what order should people
leave, and who needs a bus?* Every tunable number lives in `engine/assumptions.py` and is shown in the app's
Assumptions tab.

## Pipeline (one scenario, ~1 s)

1. **Hazard zone** (`engine/hazard.py`). ERG 2024 initial isolation circle around the release plus the
   downwind protective-action square (side = protective distance, release at the middle of its upwind edge).
   - Small spills: ERG Table 1. Large spills: ERG Table 3, **rail tank car** row, by wind band
     (low < 6 mph, moderate 6–12 mph, high > 12 mph). Chlorine rail tank car: isolate 3,000 ft; protect
     6.0 / 3.9 / 3.2 mi (day), 7.0+ / 5.6 / 4.1 mi (night). Anhydrous ammonia: isolate 1,000 ft; protect
     1.0 / 0.8 / 0.6 mi (day), 2.6 / 1.3 / 0.8 mi (night).
   - Gas arrival time at a point = straight-line distance from the release ÷ wind speed.
2. **Road rules** (`engine/evacgraph.py`). Roads inside the zone are kept (people inside must drive out
   through them) but only in directions moving away from the release; entering the zone from outside is
   blocked. Exits are intersections just outside the zone plus a 300 m buffer. Closures and contraflow
   (major roads all-outbound) are supported.
3. **Who is where** (`engine/population.py`). Per Census block: residents present, visitors (workers, game-day
   crowd), car-free residents, people who need a bus (car-free × (disability share + ½ × age-65 share)), plus
   all certified nursing-home residents.
4. **Evacuate or shelter** (`engine/decisions.py`). A block evacuates only if it can get out before the gas
   arrives: warning time (5 min) + free-flow travel time to the nearest exit × 1.5 congestion factor. Otherwise
   it shelters in place. Re-checked after departure waves are assigned.
5. **Clearance time and routes** (`engine/flow.py`). Road capacity is a rate (veh/h) and supply is a count
   (vehicles), so for a candidate duration T each road carries capacity × T. Binary search finds the smallest
   T where max-flow moves every vehicle out; min-cost flow assigns routes (with a little slack so long detours
   aren't forced); the flow is decomposed into per-neighborhood paths.
6. **Departure waves** (`engine/waves.py`). Earliest gas arrival leaves first; within a 10-minute bucket,
   neighborhoods closer to an exit go first; each wave fits within the capacity of every exit and bottleneck.
7. **Traffic simulation** (`engine/sim.py`). Link-queue model, 30 s steps: each road has a travel time and an
   outflow capacity; vehicles queue when it's full. Gives "everyone out" time, when each road backs up, the
   map animation, and queued vehicle-minutes per road (used for choke-point rankings).
8. **Buses** (`engine/buses.py`). OR-Tools capacitated vehicle routing from the Metro garage to the closest
   candidate shelter outside the danger area. Each pickup must happen before the gas arrives there; travel
   times are the simulated congested times; buses avoid the zone unless picking up. If no bus could possibly
   arrive in time, those residents shelter in place instead of being counted as "unserved".
9. **Floods** (`engine/flood.py`, `data/flood_dem.py`). The second hazard. USGS 3DEP elevation (~10 m,
   averaged to 20 m). Each lake is found as its flattened water surface; its normal level is that height
   (Mendota 258.96 m ≈ 849.6 ft, Monona 257.00 m). A **priority-flood** (Barnes et al. 2014) gives, for every
   cell, the lowest lake level at which water connects to it: water must flow there, it can't jump over higher
   ground, and the other lake is a barrier (the Tenney dam holds Mendota ~2 m above Monona). A scenario raises
   Mendota, Monona or both by *rise* meters, linearly over *peak* hours. Danger zone = land reached by the peak;
   arrival time = peak × rise-needed ÷ rise; "away" = toward ground that needs more rise (higher ground);
   flooded roads close. Steps 2–8 then run unchanged; "shelter" means stay and move to an upper floor.
10. **Batch** (`engine/batch.py`, `data/databricks/batch_scenarios.py`). Hundreds of scenarios on Databricks →
   Delta tables → AI/BI dashboard + Genie agent.

## Data (all public)

| Data | Source |
|---|---|
| Roads, rail lines, bus stops, hospitals | OpenStreetMap via OSMnx |
| Night population, housing units | 2020 Census blocks (TIGERweb) |
| Daytime population | LEHD LODES 2022 (jobs at workplace, workers at home) |
| No-vehicle households, 65+ | ACS 2022 5-year, block groups (B25044, B01001) |
| Disability | ACS 2022 5-year, tracts (B18101 — not published at block-group level) |
| Nursing homes | CMS Provider Data (average residents per day) |
| Hazard distances | DOT Emergency Response Guidebook 2024 (via NOAA CAMEO Chemicals) |
| Elevation (floods) | USGS 3DEP 1/3 arc-second via the National Map elevation service |
| Bus garage | Madison Metro Transit, 1101 E Washington Ave |
| Coordinates for garage and shelters | US Census geocoder |

Study area: about 15 × 12 km (lon −89.47 to −89.29, lat 43.015 to 43.125), out to the Beltline, so evacuees
have real exits. Derailments are placed only on rail lines within 2.5 km of the center (the isthmus core).

## Key assumptions

| Assumption | Value | Why |
|---|---|---|
| Lane capacity | 1,800 veh/h motorway … 800 secondary … 500 residential | Highway Capacity Manual ballpark |
| Missing lanes / speeds in OSM | filled by road class | 72% / 67% of edges lack tags |
| Warning → first cars moving | 5 min | |
| Wave spacing | 10 min | |
| Congestion factor for evacuate/shelter call | 1.5 × free-flow | |
| Compliance | 85% (slider 60–100%) | |
| Cars taken per car-owning household | 1.0 | |
| Buses | 20 × 60 seats, leave the garage 10 min after the alert | slider |
| Walking speed | 1.2 m/s, 0.8 m/s for 65+ | |
| Daytime density cap | 100,000 people/km² | LODES puts HQ jobs on one block |
| Flood: lake rise | linear from normal level to the peak | simple, transparent |
| Flood: highways | motorway/trunk intersections never flood | bare-earth elevation removes bridges and raised roadbeds |

## Limitations (say these out loud)

- **Not a plume model.** Zones follow ERG guidance; terrain, buildings, lake breeze and plume meandering are
  ignored. Gas arrival is distance ÷ wind speed.
- **Simplified traffic.** Point queues without spillback; no signals, turns or incidents. Good for ranking
  and orders of magnitude, not exact minutes.
- **Large zones can exceed the study area** at low wind (ERG chlorine rail-car zones are 6–7+ mi); we treat
  the study-area edge as safe.
- **Candidate shelters** (Alliant Energy Center, Madison College Truax, East and West High Schools) are large
  public buildings we chose — **not official city shelter designations**.
- **Floods are a "bathtub" model of lake level.** No rainfall runoff, storm sewers, pumps, sandbags or river
  flow speed; water reaches every connected cell below the lake level. It's an upper bound on where water can
  go. Blocks are judged at their center point.
- **Assisted-living facilities** aren't in the CMS nursing-home list, so vulnerable facilities are undercounted.
  Hospital occupancy is a placeholder (hospitals are not evacuated by bus in the model).
- **Students** aren't workers in LODES, so campus daytime population is understated.
- **Population is estimated by area**, never by individual — the app shows "areas with the most residents who
  need help", not people.

## Validation

- 98 unit/integration tests (`pytest engine/tests backend/tests`), including units checks (rate × time vs.
  count), road rules, waves vs. capacity, bus deadlines never violated, and fast/fallback routing agreement.
- Robustness: findings re-checked under 7 assumption variants (`docs/findings.md` §7).
