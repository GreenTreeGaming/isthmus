# 3-minute demo script

**Setup before you start:** backend running with `ISTHMUS_ENGINE=real`, app open at localhost:5173, Databricks
dashboard and Genie open in other tabs. Backup: screen recording of the ▶ Demo walkthrough.

## 0:00 — The problem (20 s)
> "Downtown Madison sits on a strip of land between two lakes. Rail lines run straight through it, and there are
> only a few roads out. If a tank car of chlorine derailed here, who should run — and who should stay inside?"

## 0:20 — Live: the plan (60 s) — click ▶ Demo
1. **Step 1 (light wind):** "Isthmus draws the official Emergency Response Guidebook danger zone. Orange blocks
   leave in waves — highest risk first. Purple blocks are told to **stay inside**: the gas would reach them
   before they could drive out." Click a purple block → read the "why".
2. **Step 2 (stronger wind):** "Stronger wind shrinks the zone, but the gas moves faster — so more people have
   to shelter instead of leaving."
3. Click a **bus route**: "Residents without a car get pickups — each one scheduled before the gas arrives there."

## 1:20 — Live: when it breaks (30 s)
4. **Step 4 (night, 5 buses):** "At night with 5 buses instead of 20, almost 200 people who need a ride are
   left behind — 10 buses would have reached everyone. That's the number an emergency manager needs before it happens."
5. Press **▶ Play**: "This is the traffic simulation — you can watch where the roads back up."

## 1:50 — What we found across 576 scenarios (40 s) — Planning tab or Databricks dashboard
> "One scenario isn't a plan, so we ran 576 on Databricks — every derailment point, wind direction, wind speed
> and time of day."
- "Capitol Lakes nursing home is in the danger zone in **75%** of them."
- "Metro's bus garage — where every evacuation bus starts — is in it **52%** of the time."
- "No single road is the choke point more than ~16% of the time. A fixed plan doesn't work; it has to adapt."
- Optional: ask **Genie** "Which wind direction gives the longest clearance time?"

## 2:30 — How and how honest (30 s)
> "Real data: OpenStreetMap, the 2020 Census, ACS, job data, CMS nursing homes and the official 2024 guidebook.
> We dug into the data too — the jobs data put 22,000 UW employees on one campus block, so we fixed it. And our
> findings hold when we change our biggest assumptions. It's a planning tool, not a plume model — and we list
> every limitation in the app."

## Likely judge questions
- **"How accurate is the traffic model?"** Simplified queue model — good for ranking and orders of magnitude;
  findings are stable under ±25% road capacity.
- **"Why not just evacuate everyone?"** For a fast gas release, people who can't get out before it arrives
  are safer indoors — that's also the guidebook's advice.
- **"Are these real shelters?"** Candidate large public buildings, not official designations — next step is
  plugging in the city's list.
- **"Where's Databricks?"** Batch runs, Delta tables, the AI/BI dashboard and the Genie agent.
