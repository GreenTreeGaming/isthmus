# Data contract — silver tables

Produced by `data/` (Claude A). Consumed by `engine/` (Claude B).
Format: GeoParquet files in `data/silver/<table>.parquet` (fake versions in `data/fixtures/<table>.parquet`).
Geometry columns are WGS84 (EPSG:4326). Mirrored as Delta tables in Databricks with the same columns
(geometry stored as WKT string there).

## road_nodes
| column | type | notes |
|---|---|---|
| node_id | int64 | OSM node id, unique |
| lon | float64 | |
| lat | float64 | |
| is_exit | bool | true if outside study area core (candidate safe exit); hazard-specific exits are computed by engine |

## road_edges
Directed. A two-way street is two rows.
| column | type | notes |
|---|---|---|
| edge_id | int64 | unique |
| u | int64 | from node_id |
| v | int64 | to node_id |
| length_m | float64 | |
| speed_kph | float64 | filled by road class if missing |
| lanes | int32 | per direction, filled by road class if missing |
| road_class | string | OSM highway tag: motorway, primary, secondary, tertiary, residential, ... |
| capacity_vph | float64 | lanes × per-lane flow (see engine/assumptions.py) |
| name | string | nullable |
| geometry | LineString | |

## blocks
One row per 2020 Census block in study area.
| column | type | notes |
|---|---|---|
| block_id | string | 15-digit GEOID |
| node_id | int64 | nearest road node to centroid |
| pop_night | float64 | residents |
| pop_day | float64 | residents − out-commuters + in-workers (LODES) |
| pop_gameday | float64 | pop_day + stadium crowd allocation |
| households | float64 | |
| zero_vehicle_share | float64 | 0–1, from ACS B25044 |
| disability_share | float64 | 0–1, from ACS B18101 |
| age65_share | float64 | 0–1, from ACS B01001 |
| geometry | Polygon | |

Note: drivers / walkers / need_bus counts are derived by the engine from these columns + assumptions,
so they can respond to time-of-day and compliance.

## facilities
| column | type | notes |
|---|---|---|
| facility_id | string | |
| type | string | `nursing_home` \| `hospital` \| `dorm` \| `stadium` |
| name | string | |
| node_id | int64 | nearest road node |
| residents | float64 | beds / occupancy; all nursing-home residents count as need_bus |
| lon | float64 | |
| lat | float64 | |

## pickup_points
| column | type | notes |
|---|---|---|
| pickup_id | string | |
| kind | string | `metro_stop` \| `facility` |
| node_id | int64 | |
| lon | float64 | |
| lat | float64 | |

## depots
| column | type | notes |
|---|---|---|
| depot_id | string | |
| kind | string | `bus_garage` \| `shelter` |
| name | string | |
| node_id | int64 | |
| lon | float64 | |
| lat | float64 | |

## rail_lines
| column | type | notes |
|---|---|---|
| rail_id | int64 | |
| name | string | nullable |
| geometry | LineString | where a derailment pin may be dropped |

## erg_distances
Hardcoded from the DOT Emergency Response Guidebook, Table 1 (TIH materials).
| column | type | notes |
|---|---|---|
| chemical | string | `chlorine` \| `ammonia` \| ... |
| spill_size | string | `small` \| `large` |
| time_of_day | string | `day` \| `night` |
| isolation_m | float64 | initial isolation radius |
| protect_m | float64 | downwind protective action distance |
