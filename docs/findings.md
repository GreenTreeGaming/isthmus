# Findings

Every number here comes from `data/gold/insights.json` (720-scenario batch) or `data/gold/robustness.json`
(7 assumption variants × 288 scenarios). Regenerate with:

```bash
python -m engine.batch data/silver --n-points 10 --out data/gold
python -m engine.robustness data/silver
```

**Scenario set:** 10 derailment points along the rail lines through the isthmus core × 8 wind directions ×
3 wind speeds (1.5 / 4 / 7 m/s — the ERG low / moderate / high wind bands) × night / day / game day = **720
scenarios, 0 failures**, median 0.9 s each. Chemical: chlorine, large spill (ERG 2024 Table 3, rail tank car).

## 1. Vulnerable facilities are in the danger zone more often than not

| Facility | Inside the protective-action zone |
|---|---|
| Capitol Lakes Health Center (nursing home, ~29 residents/day per CMS) | **65%** of scenarios |
| UnityPoint Health – Meriter | 59% |
| Saint Mary's Hospital | 48% |
| William S. Middleton Memorial Veterans Hospital | 36% |
| UW Health University Hospital | 34% |
| American Family Children's Hospital | 34% |

## 2. The bus depot itself is exposed

Madison Metro's garage (1101 E Washington Ave) — where every evacuation bus would start — is **inside the
danger zone in 55% of scenarios**.

## 3. Wind speed decides who can leave

| Wind | Avg. time until last car is out | Avg. people evacuating | Avg. people told to shelter |
|---|---|---|---|
| 1.5 m/s (light) | **103 min** | 28,750 | 67,091 |
| 4 m/s (moderate) | 59 min | 9,651 | 70,785 |
| 7 m/s (strong) | 39 min | 4,432 | 62,816 |

Light wind means the official ERG protective zone is ~6 mi (day) to 7+ mi (night) long, so far more people are
inside it — but the gas moves slowly, so many of them have time to drive out. Strong wind shrinks the zone but
the gas arrives fast, so most people inside are told to **shelter in place**: driving out would take longer
than the gas takes to arrive.

## 4. Where traffic jams: the south-side Beltline approaches

Roads with the most queued vehicle-minutes (top 5 per scenario), by share of scenarios:

| Road | Share |
|---|---|
| Latitude 43 Street | 14% |
| Badger Parkway | 13% |
| Petra Place | 13% |
| Landmark Place | 12% |
| Fish Hatchery Road | 11% |
| Ramp near South Park Street | 9% |
| Elm Drive (UW Lakeshore) | 9% |

Most of these sit around the Park Street / Fish Hatchery Road approaches to the Beltline on Madison's south
side — neighborhoods with one or two residential exits feeding the highway ramps. **No single road is the
choke point in more than ~14% of scenarios**: a fixed evacuation plan can't work; it has to adapt to the wind
and the derailment location.

## 5. Buses: enough at 20, not at 5

With 20 buses, on average fewer than 2 people per scenario are left without a pickup. Cut the fleet and it
breaks down — e.g. a derailment near the Capitol with light SW wind: during the day 536 people need a bus and
**5 buses leave 236 behind**; at night 477 need a bus and **5 buses leave 177 behind** (10 buses still reach
everyone in both).

## 6. The findings hold when our assumptions change

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

## 7. A data quirk we caught

LEHD LODES assigns every job of some large employers to one headquarters block — about 22,000 UW–Madison jobs
landed on a single campus block, and State of Wisconsin jobs on the Capitol. Left as-is, the model would put a
stadium's worth of cars on one city block. We cap daytime density at 100,000 people/km² (above the 99th
percentile of Madison blocks); 5 blocks were capped.
