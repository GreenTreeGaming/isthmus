"""Validate fixture or silver tables against contracts/data_schema.md."""
from __future__ import annotations
import argparse
from pathlib import Path
import geopandas as gpd
import pandas as pd
S={"road_nodes":"node_id lon lat is_exit","road_edges":"edge_id u v length_m speed_kph lanes road_class capacity_vph name geometry","blocks":"block_id node_id pop_night pop_day pop_gameday households zero_vehicle_share disability_share age65_share geometry","facilities":"facility_id type name node_id residents lon lat","pickup_points":"pickup_id kind node_id lon lat","depots":"depot_id kind name node_id lon lat","rail_lines":"rail_id name geometry","erg_distances":"chemical spill_size time_of_day isolation_m protect_m"}
def main(folder:Path)->None:
    errors=[]
    for table,cols in S.items():
        p=folder/f"{table}.parquet"
        if not p.exists(): errors.append(f"missing {p.name}"); continue
        geo="geometry" in cols; df=gpd.read_parquet(p) if geo else pd.read_parquet(p)
        if list(df.columns)!=cols.split(): errors.append(f"{table}: column mismatch")
        if geo and (df.crs is None or df.crs.to_epsg()!=4326): errors.append(f"{table}: CRS must be EPSG:4326")
    if errors: raise SystemExit("\n".join(errors))
    print(f"validated {len(S)} tables in {folder}")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",nargs="?",type=Path,default=Path(__file__).parent/"silver");main(p.parse_args().folder)
