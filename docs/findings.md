# Findings

Every number here comes from `data/gold/insights.json` (576-scenario batch — the same grid the Databricks
notebook runs, so it matches the dashboard) or `data/gold/robustness.json`
(7 assumption variants × 288 scenarios). Regenerate with:

```bash
python -m engine.batch data/silver --n-points 8 --out data/gold
python -m engine.robustness data/silver
```

**Scenario set:** 8 derailment points along the rail lines through the isthmus core × 8 wind directions ×
3 wind speeds (1.5 / 4 / 7 m/s — the ERG low / moderate / high wind bands) × night / day / game day = **576
scenarios, 0 failures**, about 1 s each. Chemical: chlorine, large spill (ERG 2024 Table 3, rail tank car).

## 1. Vulnerable facilities are in the danger zone more often than not

| Facility | Inside the protective-action zone |
|---|---|
| Capitol Lakes Health Center (nursing home, ~29 residents/day per CMS) | **75%** of scenarios |
| UnityPoint Health – Meriter | 62% |
| Saint Mary's Hospital | 49% |
| William S. Middleton Memorial Veterans Hospital | 38% |
| UW Health University Hospital | 37% |
| American Family Children's Hospital | 36% |

## 2. The bus depot itself is exposed

Madison Metro's garage (1101 E Washington Ave) — where every evacuation bus would start — is **inside the
danger zone in 52% of scenarios**.

## 3. Wind speed decides who can leave

| Wind | Avg. time until last car is out | Avg. people evacuating | Avg. people told to shelter |
|---|---|---|---|
| 1.5 m/s (light) | **105 min** | 29,900 | 68,988 |
| 4 m/s (moderate) | 59 min | 9,869 | 74,415 |
| 7 m/s (strong) | 40 min | 4,594 | 67,488 |

Light wind means the official ERG protective zone is ~6 mi (day) to 7+ mi (night) long, so far more people are
inside it — but the gas moves slowly, so many of them have time to drive out. Strong wind shrinks the zone but
the gas arrives fast, so most people inside are told to **shelter in place**: driving out would take longer
than the gas takes to arrive.

## 4. Where traffic jams: the south-side Beltline approaches

Roads with the most queued vehicle-minutes (top 5 per scenario), by share of scenarios:

| Road | Share |
|---|---|
| Latitude 43 Street | 16% |
| Badger Parkway | 14% |
| Petra Place | 13% |
| Landmark Place | 12% |
| Fish Hatchery Road | 12% |
| Ramp near South Park Street | 9% |
| Monona Drive | 9% |
| Lake Mendota Drive | 8% |
| Elm Drive (UW Lakeshore) | 8% |

Most of these sit around the Park Street / Fish Hatchery Road approaches to the Beltline on Madison's south
side — neighborhoods with one or two residential exits feeding the highway ramps. **No single road is the
choke point in more than ~16% of scenarios**: a fixed evacuation plan can't work; it has to adapt to the wind
and the derailment location.

## 5. Wind direction and time of day

- **Wind from the south (180°) is the worst case: 78 min** on average to get everyone out, vs. 56 min for wind
  from the southeast (135°) — it pushes the gas up the isthmus toward downtown and the north side.
- **Game day is the slowest time: 72 min** (vs. 65 day, 66 night), with ~94,000 people told to shelter on
  average — the stadium crowd adds to everyone else.

## 6. Buses: enough at 20, not at 5

With 20 buses, on average fewer than 2 people per scenario are left without a pickup. Cut the fleet and it
breaks down — e.g. a derailment near the Capitol with light SW wind: during the day 557 people need a bus and
**5 buses leave 257 behind**; at night 491 need a bus and **5 buses leave 191 behind** (10 buses still reach
everyone in both).

## 7. The findings hold when our assumptions change

| Variant | Avg. clearance | Light > moderate > strong wind? | Top choke points |
|---|---|---|---|
| Baseline | 65 min | ✅ 104 > 53 > 37 | South-side Beltline area |
| Compliance 60% | 58 min | ✅ | same cluster |
| Compliance 100% | 68 min | ✅ | same cluster |
| Road capacity −25% | 70 min | ✅ | same cluster |
| Road capacity +25% | 60 min | ✅ | same cluster |
| Warning takes 15 min instead of 5 | 53 min | ✅ | same cluster |
| Buses leave at 20 min instead of 10 | 65 min | ✅ | same cluster |

Facility and depot exposure depend only on geometry, so they don't change. A slower warning *lowers* clearance
time because fewer people can beat the gas — **more of them have to shelter instead**. Warning speed decides
who gets to leave.

## 8. A data quirk we caught

LEHD LODES assigns every job of some large employers to one headquarters block — about 22,000 UW–Madison jobs
landed on a single campus block, and State of Wisconsin jobs on the Capitol. Left as-is, the model would put a
stadium's worth of cars on one city block. We cap daytime density at 100,000 people/km² (above the 99th
percentile of Madison blocks); 5 blocks were capped.

## 9. Floods: when the lakes rise

Source: the `flood` key of `data/gold/insights.json` (`python -m engine.flood_batch data/silver`): Lake Mendota,
Lake Monona (+ the Yahara River below it) or both × rise 0.5 / 1 / 1.5 / 2 / 3 m × peak in 3 or 12 h × night /
day / game day = **90 scenarios, 0 failures**, plus thresholds read straight from the flood grid.

**At about +0.5 m, Lake Mendota spills across the east isthmus.** The low ground along the Yahara River fills
all at once, and with it go East Washington Avenue, East Johnson Street, East Gorham Street, Packers Avenue,
North First Street, Pennsylvania Avenue — **and Madison Metro's bus garage (+0.53 m)**. The same garage that sits
in the chemical danger zone in 52% of scenarios is also one of the first places to flood.

| Both lakes rise | Land flooded | Avg. people evacuating | Avg. people staying (upper floors) | Left without a bus |
|---|---|---|---|---|
| +0.5 m | 1.8 km² | 19 | 0 | 0 |
| +1 m | 9.1 km² | 6,764 | 293 | 0 |
| +1.5 m | 16.4 km² | 10,341 | 2,200 | 0 |
| +2 m | 19.6 km² | 13,008 | 2,984 | 0 |
| +3 m | 27.2 km² | 21,462 | 2,150 | 0 |

- **Mendota is the dangerous lake.** At +1 m, Mendota floods 3.9 km² with ~6,500 people evacuating; Monona
  floods more land (5.2 km²) but it's mostly wetland south of the lake, with ~220 people evacuating.
- **Next roads to go:** John Nolen Drive and South Blair Street (+0.96 m), North Stoughton Road (+1.35 m), South
  Park Street (+1.79 m). Candidate shelter Madison College Truax floods at +1.59 m.
- **Time isn't the problem in a flood — the garage and the roads are.** Whether the peak comes in 3 or 12 hours,
  about the same number of people evacuate (~10,300) and every bus pickup is made: water moves in hours, gas in
  minutes. What breaks first is infrastructure: the buses' garage and the main east-side roads.

The flood model is a "bathtub" upper bound: no sandbags, pumps, storm sewers or rainfall runoff (see methods).
