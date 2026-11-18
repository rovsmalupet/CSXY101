"""Add random passengers and a little other traffic to the jeepney simulation.

Run it after tools/build_from_thesis.py, which writes the roads and jeepney lines it reads:

    python tools/make_demand.py

Writes (relative to this project folder):
    network/jeepney_stops.add.xml   roadside spots where jeepneys pick up and drop off, about every SPACING_M
                                    along each line
    demand/jeepneys.rou.xml         the same lines, with a stop at every spot they pass. The stops are on
                                    demand: a jeepney only stops where someone gets on or off
    demand/passengers.rou.xml       random passengers. Each appears on the sidewalk, walks to a spot, rides
                                    any jeepney going their way for at least MIN_RIDE_M, then walks off
    demand/traffic.rou.xml          random cars and motorcycles, each coming in at one road end and leaving
                                    at another

Needs SUMO (SUMO_HOME set, for sumolib). Running it again gives the same files: the passengers and spots
come from a fixed seed (--seed), and the old stops of the jeepney lines are replaced.
"""

import argparse
import math
import os
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if os.environ.get("SUMO_HOME"):
    sys.path.append(str(Path(os.environ["SUMO_HOME"]) / "tools"))
import sumolib  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
NET = HERE / "network" / "santarosa_3brgy.net.xml"
JEEPNEYS = HERE / "demand" / "jeepneys.rou.xml"
STOPS = HERE / "network" / "jeepney_stops.add.xml"
PASSENGERS = HERE / "demand" / "passengers.rou.xml"
TRAFFIC = HERE / "demand" / "traffic.rou.xml"

SPACING_M = 200                    # a pickup spot about every 200 m along each line
SPOT_LENGTH_M = 15                 # room for one jeepney (7 m) and its gap
EDGE_MARGIN_M = 5                  # keep spots this far from the ends of a road piece (crosswalks, junctions)
FIRST_SPOT_M = 60                  # no spot in a line's first 60 m: its jeepneys come in at full speed
STOP_S = 5                         # a jeepney stops at least 5 s; boarding adds 2 s per passenger (vType)
MIN_RIDE_M = 300                   # nobody rides a jeepney for less than this
PASSENGERS_PER_HOUR = 240          # one new passenger every 15 s on average, all day
VEHICLES_PER_HOUR = 120            # cars and motorcycles coming in at each road end, all day
MOTORCYCLE_SHARE = 0.7             # the thesis's Balibago count: 40,284 motorcycles to 17,556 cars
END_S = 86400                      # a whole day, as the jeepneys
SEED = 42
SHORT = {"National Highway 1": "N1", "Rizal Boulevard": "RIZ", "Felix Reyes Street": "FRS"}
# the thesis's car and motorcycle (its generated/vtypes.add.xml, from make_vtypes.py)
VTYPES = [
    '<vType id="car" vClass="passenger" latAlignment="nice" minGapLat="0.4" color="0.75,0.75,0.75"/>',
    '<vType id="motorcycle" vClass="motorcycle" width="0.75" latAlignment="arbitrary" minGapLat="0.15" '
    'color="0.1,0.9,0.9" guiShape="motorcycle"/>',
]


def road_lane(edge):
    """The rightmost lane jeepneys drive in (lane 0 is the sidewalk)."""
    return next(lane for lane in edge.getLanes() if lane.allows("bus"))


def sidewalk(edge):
    return next(lane for lane in edge.getLanes() if lane.allows("pedestrian"))


def offsets(net, edges):
    """Where each edge of a route starts, in metres along the route, and the route's length."""
    out, total = [], 0.0
    for eid in edges:
        out.append(total)
        total += road_lane(net.getEdge(eid)).getLength()
    return out, total


def place_spots(net, routes):
    """Spots along every line, about SPACING_M apart. Lines sharing a road share its spots."""
    spots = []                                                   # [{id, edge, lane, start, end, name}]

    for edges in routes.values():
        offs, total = offsets(net, edges)
        index = {eid: k for k, eid in enumerate(edges)}

        def along(spot):
            return offs[index[spot["edge"]]] + spot["end"]

        last = FIRST_SPOT_M - SPACING_M
        while last + SPACING_M <= total - EDGE_MARGIN_M:
            target = last + SPACING_M
            lo, hi = last + SPACING_M / 2, target + SPACING_M / 2
            near = [along(s) for s in spots if s["edge"] in index and lo < along(s) <= hi]
            if near:                                             # another line already put one here
                last = min(near, key=lambda d: abs(d - target))
                continue
            best = None
            for k, eid in enumerate(edges):                      # the road piece nearest the target with room
                lane = road_lane(net.getEdge(eid))
                length = lane.getLength()
                if length < SPOT_LENGTH_M + 2 * EDGE_MARGIN_M:
                    continue
                end = min(max(target - offs[k] + SPOT_LENGTH_M / 2, SPOT_LENGTH_M + EDGE_MARGIN_M),
                          length - EDGE_MARGIN_M)
                d = offs[k] + end
                taken = any(s["edge"] == eid and abs(s["end"] - end) < SPOT_LENGTH_M for s in spots)
                if lo < d <= hi and d >= FIRST_SPOT_M and not taken and \
                        (best is None or abs(d - target) < abs(best[0] - target)):
                    best = (d, eid, lane, end)
            if best is None:                                     # no room near here: try further on
                last = target
                continue
            d, eid, lane, end = best
            spots.append({"id": f"spot_{len(spots)}", "edge": eid, "lane": lane.getID(), "start": end - SPOT_LENGTH_M,
                          "end": end, "name": net.getEdge(eid).getName()})
            last = d
    return spots


def stops_of(net, routes, spots):
    """Each line's spots in driving order, as [(metres along the route, spot)]."""
    out = {}
    for rid, edges in routes.items():
        offs, _ = offsets(net, edges)
        index = {eid: k for k, eid in enumerate(edges)}
        on = [(offs[index[s["edge"]]] + s["end"], s) for s in spots if s["edge"] in index]
        out[rid] = sorted([(d, s) for d, s in on if d >= FIRST_SPOT_M], key=lambda x: x[0])
    return out


def write_jeepneys(tree, prolog, route_stops):
    """Put an on-demand stop at every spot into each jeepney route (replacing earlier ones)."""
    root = tree.getroot()
    for c in list(root):
        if c.tag is ET.Comment and c.text.strip().startswith("Stops:"):
            root.remove(c)
    root.insert(0, ET.Comment(" Stops: added by tools/make_demand.py. Each route stops at every pickup spot on its way\n"
                              "         (network/jeepney_stops.add.xml), but only when someone gets on or off there\n"
                              f"         (onDemand), for at least {STOP_S} s. "))
    for r in root.iter("route"):
        for old in r.findall("stop"):
            r.remove(old)
        for _, s in route_stops[r.get("id")]:
            ET.SubElement(r, "stop", busStop=s["id"], duration=str(STOP_S), onDemand="true")
    ET.indent(tree, "    ")
    body = ET.tostring(root, encoding="unicode").replace(" />", "/>")
    JEEPNEYS.write_text(prolog + body + "\n", encoding="utf-8")


def write_spots(spots, served_by):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           "<!-- Generated by tools/make_demand.py: roadside spots where jeepneys pick up and drop off passengers,",
           f"     about every {SPACING_M} m along each line. -->",
           "<additional>"]
    for s in spots:
        xml.append(f'    <busStop id="{s["id"]}" name="{s["name"]}" lane="{s["lane"]}" startPos="{s["start"]:.2f}" '
                   f'endPos="{s["end"]:.2f}" lines="{" ".join(served_by[s["id"]])}" personCapacity="30"/>')
    xml.append("</additional>")
    STOPS.write_text("\n".join(xml) + "\n", encoding="utf-8")


def write_passengers(net, lines, route_stops, rng, per_hour):
    """Passengers appearing at random times, at random spots, riding to a random later spot."""
    order = {}                                                   # line -> {spot id: position in its stops}
    for line, rid in lines.items():
        order[line] = {s["id"]: k for k, (_, s) in enumerate(route_stops[rid])}
    trips = {}                                                   # spot id -> [(line, [spots at least MIN_RIDE_M on])]
    for line, rid in lines.items():
        rs = route_stops[rid]
        for k, (d, s) in enumerate(rs):
            later = [t for dt, t in rs[k + 1:] if dt - d >= MIN_RIDE_M]
            if later:
                trips.setdefault(s["id"], []).append((line, later))
    spot_ids = sorted(trips, key=lambda sid: int(sid.split("_")[1]))
    spot = {s["id"]: s for _, rs in route_stops.items() for _, s in rs}

    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           f"<!-- Generated by tools/make_demand.py: random passengers, {per_hour} an hour on average, all day.",
           "     Each appears on the sidewalk, walks to a pickup spot, rides any jeepney going their way at least",
           f"     {MIN_RIDE_M} m and walks off. -->",
           "<routes>"]
    t, n = rng.expovariate(per_hour / 3600), 0
    while t < END_S:
        a = rng.choice(spot_ids)
        _, later = rng.choice(trips[a])
        b = rng.choice(later)["id"]
        ride = [line for line in lines if a in order[line] and b in order[line] and order[line][a] < order[line][b]]
        walk_from = sidewalk(net.getEdge(spot[a]["edge"])).getLength()
        walk_to = sidewalk(net.getEdge(spot[b]["edge"])).getLength()
        xml += [f'    <person id="p{n}" depart="{t:.2f}" departPos="{rng.uniform(0, walk_from):.2f}">',
                f'        <walk edges="{spot[a]["edge"]}" busStop="{a}"/>',
                f'        <ride busStop="{b}" lines="{" ".join(ride)}"/>',
                f'        <walk edges="{spot[b]["edge"]}" arrivalPos="{rng.uniform(0, walk_to):.2f}"/>',
                "    </person>"]
        t += rng.expovariate(per_hour / 3600)
        n += 1
    xml.append("</routes>")
    PASSENGERS.write_text("\n".join(xml) + "\n", encoding="utf-8")
    return n


def road_ends(net, routes):
    """The road ends: where the jeepney lines come in and go out. Returns ({in edge: name}, {out edge: name})."""
    ins = list(dict.fromkeys(edges[0] for edges in routes.values()))
    outs = list(dict.fromkeys(edges[-1] for edges in routes.values()))
    where = {e: net.getEdge(e).getFromNode().getCoord() for e in ins}
    where.update({e: net.getEdge(e).getToNode().getCoord() for e in outs})
    street = {e: net.getEdge(e).getName() for e in ins + outs}

    def name(e):
        same = [o for o in ins if street[o] == street[e]]
        short = SHORT.get(street[e], street[e].replace(" ", "-") or e)
        if len(same) < 2:
            return short
        xs, ys = [where[o][0] for o in same], [where[o][1] for o in same]
        if max(ys) - min(ys) >= max(xs) - min(xs):
            return short + ("-north" if where[e][1] >= sum(ys) / len(ys) else "-south")
        return short + ("-east" if where[e][0] >= sum(xs) / len(xs) else "-west")

    in_names = {e: name(e) for e in ins}
    out_names = {}
    for e in outs:                                               # an exit is named after the entry beside it
        nearest = min(ins, key=lambda i: math.dist(where[i], where[e]))
        out_names[e] = in_names[nearest]
    return in_names, out_names


def write_traffic(net, routes, per_hour):
    ins, outs = road_ends(net, routes)
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           f"<!-- Generated by tools/make_demand.py: a little other traffic. {per_hour} cars and motorcycles an hour",
           f"     come in at each road end, {MOTORCYCLE_SHARE:.0%} of them motorcycles, at random times (exponential",
           "     gaps), each going out at another road end. -->",
           "<routes>"]
    xml += ["    " + v for v in VTYPES]
    flows = 0
    for a, a_name in ins.items():
        exits = [b for b, b_name in outs.items() if b_name != a_name
                 and all(net.getShortestPath(net.getEdge(a), net.getEdge(b), vClass=vc)[0]
                         for vc in ("passenger", "motorcycle"))]
        for b in exits:
            for vtype, share in (("motorcycle", MOTORCYCLE_SHARE), ("car", 1 - MOTORCYCLE_SHARE)):
                rate = per_hour * share / len(exits) / 3600     # vehicles a second
                xml.append(f'    <flow id="{vtype}_{a_name}_to_{outs[b]}" type="{vtype}" from="{a}" to="{b}" '
                           f'begin="0" end="{END_S}" period="exp({rate:.6f})" departLane="best" departSpeed="max"/>')
                flows += 1
    xml.append("</routes>")
    TRAFFIC.write_text("\n".join(xml) + "\n", encoding="utf-8")
    return ins, flows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--passengers", type=float, default=PASSENGERS_PER_HOUR,
                    help=f"new passengers an hour, all day (default {PASSENGERS_PER_HOUR})")
    ap.add_argument("--vehicles", type=float, default=VEHICLES_PER_HOUR,
                    help=f"cars and motorcycles an hour coming in at each road end (default {VEHICLES_PER_HOUR})")
    ap.add_argument("--seed", type=int, default=SEED, help=f"for the random passengers (default {SEED})")
    args = ap.parse_args()

    net = sumolib.net.readNet(str(NET))
    text = JEEPNEYS.read_text(encoding="utf-8")
    prolog = text[:text.index("<routes")]
    tree = ET.ElementTree(ET.fromstring(text[len(prolog):], ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))))
    routes = {r.get("id"): r.get("edges").split() for r in tree.getroot().iter("route")}
    lines = {f.get("line"): f.get("route") for f in tree.getroot().iter("flow")}

    spots = place_spots(net, routes)
    route_stops = stops_of(net, routes, spots)
    served_by = {s["id"]: [line for line, rid in lines.items() if any(t is s for _, t in route_stops[rid])]
                 for s in spots}
    write_spots(spots, served_by)
    write_jeepneys(tree, prolog, route_stops)
    n = write_passengers(net, lines, route_stops, random.Random(args.seed), args.passengers)
    ends, flows = write_traffic(net, routes, args.vehicles)

    print(f"Wrote {STOPS.relative_to(HERE)}: {len(spots)} pickup spots")
    for line, rid in lines.items():
        print(f"  {line:12s} stops at {len(route_stops[rid])} spots")
    print(f"Wrote {JEEPNEYS.relative_to(HERE)}: the same lines, with on-demand stops")
    print(f"Wrote {PASSENGERS.relative_to(HERE)}: {n} passengers")
    print(f"Wrote {TRAFFIC.relative_to(HERE)}: {flows} flows from {len(ends)} road ends ({', '.join(ends.values())})")


if __name__ == "__main__":
    main()
