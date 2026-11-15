# Databricks notebook source
# MAGIC %md
# MAGIC # Isthmus — batch derailment scenarios
# MAGIC Runs the evacuation engine on hundreds of simulated train derailments around downtown Madison and saves
# MAGIC the results as Delta tables for the AI/BI dashboard and the Genie agent.
# MAGIC
# MAGIC **Setup:** add this repo as a Git folder (Workspace → Create → Git folder), open this notebook from the repo,
# MAGIC attach **Serverless** compute, Run all. ~10 min for the default grid.

# COMMAND ----------

# MAGIC %pip install osmnx ortools networkx geopandas shapely pyproj scipy
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import sys

# This notebook lives in data/databricks/, the repo root is two levels up.
REPO = os.path.abspath(os.path.join(os.getcwd(), "..", "..")) if os.getcwd().endswith("databricks") else os.getcwd()
sys.path.insert(0, REPO)
SILVER = f"{REPO}/data/silver"

from engine.network import load_network

net = load_network(SILVER, use_cache=False)
print(net.G.number_of_nodes(), "intersections,", len(net.blocks), "blocks")   # expect 5441, 2113

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scenario grid
# MAGIC 8 derailment points along the rail lines in the isthmus core × 8 wind directions × 3 wind speeds
# MAGIC (ERG low / moderate / high bands) × night / day / game day = **576 scenarios**.

# COMMAND ----------

import pandas as pd

from engine.batch import run_row, scenario_grid

grid = scenario_grid(net, n_points=8)
rows = []
for i, (_, r) in enumerate(grid.iterrows()):
    rows.append(run_row(r, net))
    if i % 50 == 0:
        print(i, "/", len(grid))
results = pd.DataFrame(rows)

spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.isthmus")
(spark.createDataFrame(results).write.mode("overwrite").option("overwriteSchema", "true")
      .saveAsTable("workspace.isthmus.scenario_results"))
print("failed:", results["error"].notna().sum())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold tables (dashboard + Genie)

# COMMAND ----------

from engine.batch import gold_tables

gold = gold_tables(results, net)
ins = gold["insights"]
for name in ["top_bottlenecks", "facilities_in_zone", "worst_wind", "by_time_of_day", "by_wind_speed",
             "binding_limits"]:
    (spark.createDataFrame(pd.DataFrame(ins[name])).write.mode("overwrite")
          .option("overwriteSchema", "true").saveAsTable(f"workspace.isthmus.gold_{name}"))
(spark.createDataFrame(gold["block_frequency"]).write.mode("overwrite")
      .option("overwriteSchema", "true").saveAsTable("workspace.isthmus.gold_block_frequency"))
print("Metro garage inside the danger zone in", round(ins["garage_in_zone_share"] * 100, 1), "% of scenarios")
display(pd.DataFrame(ins["top_bottlenecks"]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Floods: when the lakes rise
# MAGIC Lake Mendota, Lake Monona (+ Yahara River) or both × rise 0.5–3 m × peak in 3 or 12 h × night / day / game day
# MAGIC = **90 scenarios**, using the flood grid in `data/silver/flood_grid.npz` (USGS 3DEP elevation + priority-flood).
# MAGIC Plus thresholds: how far the lakes must rise before the Metro garage, shelters, hospitals and major roads flood.

# COMMAND ----------

from engine.flood_batch import flood_grid, flood_insights, run_flood_row

fgrid = flood_grid()
fres = pd.DataFrame([run_flood_row(r, net) for _, r in fgrid.iterrows()])
(spark.createDataFrame(fres).write.mode("overwrite").option("overwriteSchema", "true")
      .saveAsTable("workspace.isthmus.flood_results"))
fins = flood_insights(fres, net)
for name in ["by_rise", "by_source", "facilities", "roads"]:
    (spark.createDataFrame(pd.DataFrame(fins[name])).write.mode("overwrite")
          .option("overwriteSchema", "true").saveAsTable(f"workspace.isthmus.gold_flood_{name}"))
print("failed:", fres["error"].notna().sum(), "| Metro garage floods at +", fins["garage_flood_rise_m"], "m")
display(pd.DataFrame(fins["roads"]))
