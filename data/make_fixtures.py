"""Create deterministic, synthetic GeoParquet fixtures for local development."""
from __future__ import annotations
from pathlib import Path
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

OUT = Path(__file__).parent / "fixtures"
CRS = "EPSG:4326"

def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    nodes = []
    for r in range(5):
        for c in range(6):
            lon, lat = -89.378 + .0032*c, 43.073 + .0035*r
            nodes.append(dict(node_id=1000+r*10+c, lon=lon, lat=lat, is_exit=c in (0,5) or r in (0,4)))
    node_df = pd.DataFrame(nodes).astype({"node_id":"int64","lon":"float64","lat":"float64","is_exit":"bool"})
    node_df.to_parquet(OUT / "road_nodes.parquet", index=False)
    pos = node_df.set_index("node_id")
    links = [(1000+r*10+c,1000+r*10+c+1,"primary" if r==2 else "secondary",["John Nolen Dr","W Wilson St","E Washington Ave","University Ave","E Johnson St"][r]) for r in range(4) for c in range(5)]
    links += [(1000+r*10+2,1000+(r+1)*10+2,"tertiary","N Blair St") for r in range(4)] + [(1040,1041,"tertiary","E Johnson St")]
    edges=[]
    for i,(u,v,klass,name) in enumerate(links,1):
        for a,b in ((u,v),(v,u)):
            pa,pb=pos.loc[a],pos.loc[b]; geom=LineString([(pa.lon,pa.lat),(pb.lon,pb.lat)])
            lanes=2 if klass in ("primary","secondary") else 1
            edges.append(dict(edge_id=i*10+(a!=u),u=a,v=b,length_m=geom.length*111000,speed_kph=56. if klass=="primary" else 48. if klass=="secondary" else 40.,lanes=lanes,road_class=klass,capacity_vph=float(lanes*800),name=name,geometry=geom))
    gpd.GeoDataFrame(edges,crs=CRS).to_parquet(OUT / "road_edges.parquet",index=False)
    blocks=[]
    for i,n in enumerate([1011,1012,1013,1014,1021,1022,1023,1031,1032,1033]):
        p=pos.loc[n]; x,y=p.lon,p.lat; night=float(110+23*i); day=night*(.82+(i%3)*.12)
        blocks.append(dict(block_id=f"55025001604{1000+i:04d}",node_id=n,pop_night=night,pop_day=day,pop_gameday=day+(7500. if i in (2,3,4) else 0.),households=night/2.15,zero_vehicle_share=.08+.018*i,disability_share=.07+.025*(i%4),age65_share=.09+.03*(i%5),geometry=Polygon([(x-.00065,y-.00055),(x+.00065,y-.00055),(x+.00065,y+.00055),(x-.00065,y+.00055)])))
    gpd.GeoDataFrame(blocks,crs=CRS).to_parquet(OUT / "blocks.parquet",index=False)
    def xy(n:int)->tuple[float,float]: return tuple(pos.loc[n,["lon","lat"]])
    facilities=pd.DataFrame([("fac_nh_01","nursing_home","Capitol Lakes",1012,175.),("fac_nh_02","nursing_home","Oakwood Madison",1022,120.),("fac_hosp_01","hospital","UW Health East Madison",1033,250.)],columns=["facility_id","type","name","node_id","residents"])
    facilities[["lon","lat"]]=pd.DataFrame([xy(n) for n in facilities.node_id], index=facilities.index); facilities.to_parquet(OUT/"facilities.parquet",index=False)
    pickups=pd.DataFrame([(f"metro_{i:02d}","metro_stop",n,*xy(n)) for i,n in enumerate([1001,1011,1014,1021,1024],1)],columns=["pickup_id","kind","node_id","lon","lat"]); pickups.to_parquet(OUT/"pickup_points.parquet",index=False)
    depots=pd.DataFrame([( "garage_main","bus_garage","Metro Transit Garage",1000,*xy(1000)),("shelter_east","shelter","Eastside Community Shelter",1045,*xy(1045))],columns=["depot_id","kind","name","node_id","lon","lat"]); depots.to_parquet(OUT/"depots.parquet",index=False)
    gpd.GeoDataFrame([dict(rail_id=1,name="Wisconsin & Southern Railway",geometry=LineString([(-89.378,43.074),(-89.370,43.079),(-89.362,43.087)]))],crs=CRS).to_parquet(OUT/"rail_lines.parquet",index=False)
    pd.DataFrame([
        ("chlorine","small","day",30.,1100.), ("chlorine","small","night",30.,3400.),
        ("chlorine","large","day",100.,8000.), ("chlorine","large","night",100.,21000.),
        ("ammonia","small","day",30.,1000.), ("ammonia","small","night",30.,2200.),
        ("ammonia","large","day",60.,5500.), ("ammonia","large","night",60.,12000.),
    ],columns=["chemical","spill_size","time_of_day","isolation_m","protect_m"]).to_parquet(OUT/"erg_distances.parquet",index=False)
if __name__ == "__main__": build()
