# Jeepney ABM: Macabling, Pooc and Balibago

A small SUMO simulation of three barangays of Santa Rosa, Laguna: **Macabling, Pooc (Pook) and
Balibago**. It has only the roads jeepneys run on there, cut at the barangay boundaries, the
jeepneys driving them in both directions, random passengers riding them, and a little other traffic.

## Run it

You need [SUMO](https://eclipse.dev/sumo/) (tested with 1.27.0). From this folder:

```bash
sumo-gui -c jeepney.sumocfg                                  # opens the map; press play
sumo -c jeepney.sumocfg --tripinfo-output tripinfo.xml       # no window: every trip in tripinfo.xml
```

`tripinfo.xml` has each vehicle's trip, and each passenger's walk, wait and ride. Add
`--stop-output stops.xml` to see where each jeepney stopped and who got on or off.

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
- They pick up and drop off passengers at roadside spots along the way (below). With passengers and other traffic, a trip takes 1 to 2 minutes longer than in the table.

To change how often jeepneys come, edit `period` (seconds) in each `<flow>` of `demand/jeepneys.rou.xml`.

## The passengers

Random passengers, 240 an hour on average (one every 15 s), all day: 5,784 in a day.

- **Pickup spots:** 44 roadside spots, about every 200 m along each line, on both sides of each road (`network/jeepney_stops.add.xml`). Lines on the same road share its spots.
- Each passenger appears at a random time on the sidewalk next to a random spot, walks to it and waits. They take the first jeepney with a free seat going their way (any line that stops at both spots). They ride at least 300 m to a random later spot, then walk off along the sidewalk.
- A jeepney stops at a spot only when someone is waiting there for it, or someone on board gets off there (SUMO's on-demand stops). It stops for at least 5 s, plus 2 s for each passenger getting on.
- This is SUMO's own boarding, not the agent-based part yet: nobody flags a jeepney down or decides anything.

In a whole day with the defaults, passengers waited 2.5 min for a jeepney on average and rode 850 m.
Jeepneys stopped 7,641 times and drove past 8,766 spots where nobody was getting on or off. At most
11 of the 22 seats were taken.

## Other traffic

A little other traffic, so the jeepneys aren't alone on the road. 120 vehicles an hour come in at
each of the four road ends (National Highway 1 north and south, Rizal Boulevard and Felix Reyes
Street), 480 an hour in all, at random times. Each goes out at one of the other three road ends.

- 70% are motorcycles and 30% cars, the share in the thesis's Balibago traffic count.
- They use the thesis's `car` and `motorcycle` types. Motorcycles can squeeze past jeepneys in the same lane (sublanes).
- They enter already moving, like the jeepneys.
- SUMO warns of a few collisions a day: 6 with the defaults, 1 without passengers. They happen when a car moves in beside a jeepney slowing for a spot (sublanes). Collisions only give a warning (`collision.action`): nobody is removed.

To change the number of passengers or vehicles, run for example
`python tools/make_demand.py --passengers 120 --vehicles 60` (both per hour).

## Files

| File | What it is |
|---|---|
| `jeepney.sumocfg` | The simulation: which files to load, one whole day, sublanes of 0.4 m |
| `network/santarosa_3brgy.net.xml` | The roads |
| `network/barangays.poly.xml` | The three barangay outlines, drawn in sumo-gui |
| `network/jeepney_stops.add.xml` | The 44 pickup spots |
| `demand/jeepneys.rou.xml` | The jeepney type, the six routes with their stops, and a flow for each |
| `demand/passengers.rou.xml` | The random passengers: where each one appears, gets on and gets off |
| `demand/traffic.rou.xml` | The car and motorcycle types and their flows between the road ends |
| `data/barangays.geojson` | The three barangay boundaries (longitude, latitude) |
| `tools/build_from_thesis.py` | How the roads and jeepneys were made (below) |
| `tools/make_demand.py` | How the pickup spots, passengers and other traffic were made (below) |

## How it was made

`tools/build_from_thesis.py` takes the SUMO network and jeepney lines of the PASADA thesis
project (its `starosa_bayan` folder). It keeps only the edges those lines drive, plus the other
direction of each road. It cuts them where they leave the three barangays and writes every file
above. It isn't needed to run the simulation. To make the files again, with SUMO, `shapely` and
`pyproj` installed:

```bash
python tools/build_from_thesis.py --thesis ../PASADA-abm-starosa-bayan/starosa_bayan
```

`tools/make_demand.py` then adds the pickup spots, the jeepneys' stops, the passengers and the
other traffic. It only needs SUMO, and always gives the same files (the randomness has a fixed
seed). Run it again after `build_from_thesis.py`, which writes the jeepney routes without stops:

```bash
python tools/make_demand.py
```

## Sources

- Roads: © OpenStreetMap contributors, ODbL. Downloaded 2026-10-16.
- Barangay boundaries: NAMRIA and PSA, via OCHA's COD-AB on HDX, CC BY-IGO 3.0. Valid on 2025-02-13.
- Jeepney routes: the PASADA thesis project's lines, from a group member who lives in the area.
