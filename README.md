# Jeepney ABM: Macabling, Pooc and Balibago

A small SUMO simulation of three barangays of Santa Rosa, Laguna: **Macabling, Pooc (Pook) and
Balibago**. It has only the roads jeepneys run on there, cut at the barangay boundaries, and the
jeepneys driving them in both directions.

## Run it

You need [SUMO](https://eclipse.dev/sumo/) (tested with 1.27.0). From this folder:

```bash
sumo-gui -c jeepney.sumocfg                                  # opens the map; press play
sumo -c jeepney.sumocfg --tripinfo-output tripinfo.xml       # no window: each jeepney's trip in tripinfo.xml
```

The simulation runs a whole day (0 to 86,400 s). Add `--end 3600` to stop after one hour.

## The roads

| Road | Length | Barangays |
|---|---|---|
| National Highway 1 | 1.63 km | Macabling, Pooc, Balibago |
| Felix Reyes Street | 1.94 km | Balibago |
| Rizal Boulevard | 0.93 km | Pooc, Balibago |

- Both directions of each road, with their lanes and sidewalks from OpenStreetMap.
- Speed limits: 40 km/h on national roads and 30 km/h on city streets, unless OpenStreetMap says otherwise (RA 4136, JMC 2018-001).
- Seven traffic lights. Every side street was removed, so six of them only stop traffic for the crosswalk, 10 s every 90 s. The light where National Highway 1 meets Felix Reyes Street keeps its full cycle.
- National Highway 1 is the boundary between Macabling and Labas for about 800 m. So a road counts as inside when it is within 10 m of the three barangays. Each road end is therefore 10 m past the boundary.
- Other main roads in these barangays have no jeepney line in the source data (below), so they're left out. These are Mamplasan Road, RSBS Boulevard and Macabling Road.

## The jeepneys

Six lines, each road route in both directions. Each line runs one jeepney every 5 minutes, all
day.

| Line | Route | Length | Time (no other traffic) |
|---|---|---|---|
| `N1_S`, `N1_N` | National Highway 1 | 1.8 km | about 3 min |
| `RIZ-FRS_S`, `RIZ-FRS_N` | Rizal Boulevard and Felix Reyes Street | 2.8–3.0 km | about 5.5 min |
| `RIZ-N1_S`, `RIZ-N1_N` | Rizal Boulevard and National Highway 1 | 1.2–1.3 km | about 2.5 min |

- Vehicle type `jeepney`: 7 m long, 2.1 m wide, 22 seats, top speed 60 km/h, yellow.
- Jeepneys enter at one road end already moving, as if they came from outside, and leave at the other end.
- **They don't pick anyone up yet.** There are no commuters in the simulation. Adding them, and making jeepneys stop when someone flags them down, is the agent-based part still to build.

To change how often jeepneys come, edit `period` (seconds) in each `<flow>` of `demand/jeepneys.rou.xml`.

## Files

| File | What it is |
|---|---|
| `jeepney.sumocfg` | The simulation: which files to load, one whole day, sublanes of 0.4 m |
| `network/santarosa_3brgy.net.xml` | The roads |
| `network/barangays.poly.xml` | The three barangay outlines, drawn in sumo-gui |
| `demand/jeepneys.rou.xml` | The jeepney type, the six routes and a flow for each |
| `data/barangays.geojson` | The three barangay boundaries (longitude, latitude) |
| `tools/build_from_thesis.py` | How all of the above was made (below) |

## How it was made

`tools/build_from_thesis.py` takes the SUMO network and jeepney lines of the PASADA thesis
project (its `starosa_bayan` folder). It keeps only the edges those lines drive, plus the other
direction of each road. It cuts them where they leave the three barangays and writes every file
above. It isn't needed to run the simulation. To make the files again, with SUMO, `shapely` and
`pyproj` installed:

```bash
python tools/build_from_thesis.py --thesis ../PASADA-abm-starosa-bayan/starosa_bayan
```

## Sources

- Roads: © OpenStreetMap contributors, ODbL. Downloaded 2026-10-16.
- Barangay boundaries: NAMRIA and PSA, via OCHA's COD-AB on HDX, CC BY-IGO 3.0. Valid on 2025-02-13.
- Jeepney routes: the PASADA thesis project's lines, from a group member who lives in the area.
