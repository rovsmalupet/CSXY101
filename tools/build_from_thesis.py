"""Build this project's SUMO files from the thesis's starosa_bayan network (PASADA-abm).

Keeps only the roads the thesis's jeepney lines drive, and only inside three barangays of
Santa Rosa, Laguna: Macabling, Pooc (Pook) and Balibago. Roads are cut where they leave the three
barangays. A road counts as inside when it is within EDGE_TOLERANCE_M of them: National Highway 1
runs along the Macabling-Labas boundary, crossing it back and forth by a few metres, and would
otherwise fall apart into short pieces. Both directions of a road are kept.

The jeepneys are the thesis's: the same vehicle type (make_vtypes.py), the same lines in both
directions (make_routes.py, settings.JEEPNEY_LINES), cut to the part inside the three barangays, and
one jeepney per line every HEADWAY_S, entering already moving, as the thesis's do.

Writes (relative to this project folder):
    network/santarosa_3brgy.net.xml   the roads
    network/barangays.poly.xml        the three barangay outlines, for sumo-gui
    demand/jeepneys.rou.xml           the jeepney type, lines and flows
    data/barangays.geojson            the three barangay boundaries (lon/lat)
    jeepney.sumocfg                   the simulation

Needs SUMO (netconvert on PATH or SUMO_HOME set), shapely and pyproj. The thesis folder must have
bayan.net.xml and generated/ (python build.py there). Run from anywhere:

    python tools/build_from_thesis.py --thesis ../PASADA-abm-starosa-bayan/starosa_bayan

Then run tools/make_demand.py: the simulation also loads the pickup spots, passengers and other traffic
it writes, and it puts the jeepneys' stops back into demand/jeepneys.rou.xml.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent.parent
BARANGAYS = {                      # adm4_pcode in the thesis's santa_rosa_barangays.geojson
    "PH0403428009": "Macabling",
    "PH0403428016": "Pooc",        # "Pook" in the boundary file
    "PH0403428002": "Balibago",
}
COLORS = {"Macabling": "0.85,0.35,0.35", "Pooc": "0.30,0.60,0.90", "Balibago": "0.35,0.75,0.35"}
EDGE_TOLERANCE_M = 10.0            # a road this close to the three barangays counts as inside
MIN_PIECE_M = 1.0                  # shorter bits of a cut road are dropped
HEADWAY_S = 300                    # one jeepney per line every 5 min (thesis: JEEPNEY_HEADWAY_S)
END_S = 86400                      # a whole day
NET = HERE / "network" / "santarosa_3brgy.net.xml"
POLY = HERE / "network" / "barangays.poly.xml"
ROUTES = HERE / "demand" / "jeepneys.rou.xml"
GEOJSON = HERE / "data" / "barangays.geojson"
CONFIG = HERE / "jeepney.sumocfg"


def netconvert():
    found = shutil.which("netconvert")
    if found:
        return found
    if os.environ.get("SUMO_HOME"):
        return str(Path(os.environ["SUMO_HOME"]) / "bin" / "netconvert")
    raise SystemExit("netconvert not found: install SUMO and set SUMO_HOME")


def twin(edge_id):
    return edge_id[1:] if edge_id.startswith("-") else "-" + edge_id


def pieces_of(line, area):
    """The parts of line inside area, in driving order, each as a LineString running the same way."""
    cut = line.intersection(area)
    parts = [p for g in getattr(cut, "geoms", [cut]) if g.geom_type in ("LineString", "MultiLineString")
             for p in getattr(g, "geoms", [g]) if not p.is_empty]
    merged = shapely.line_merge(shapely.MultiLineString(parts)) if parts else None
    out = []
    for p in getattr(merged, "geoms", [merged] if merged is not None and not merged.is_empty else []):
        if p.length < MIN_PIECE_M:
            continue
        if line.project(Point(p.coords[0])) > line.project(Point(p.coords[-1])):
            p = LineString(p.coords[::-1])
        out.append(p)
    return sorted(out, key=lambda p: line.project(Point(p.coords[0])))


def fmt(coords):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thesis", required=True, help="the thesis's starosa_bayan folder")
    args = ap.parse_args()
    thesis = Path(args.thesis).resolve()
    for need in ("bayan.net.xml", "generated/jeepney_routes.json", "generated/vtypes.add.xml",
                 "data/santa_rosa_barangays.geojson"):
        if not (thesis / need).is_file():
            raise SystemExit(f"Missing {thesis / need} (run python build.py in the thesis folder)")

    tmp = Path(tempfile.mkdtemp(prefix="jeepney_abm_"))
    try:
        # 1. the thesis network as plain XML (nodes, edges, connections)
        subprocess.run([netconvert(), "-s", str(thesis / "bayan.net.xml"), "--plain-output-prefix",
                        str(tmp / "bayan")], check=True, capture_output=True)
        nod = ET.parse(tmp / "bayan.nod.xml")
        edg = ET.parse(tmp / "bayan.edg.xml")
        con = ET.parse(tmp / "bayan.con.xml")
        loc = nod.getroot().find("location")
        ox, oy = map(float, loc.get("netOffset").split(","))
        proj = Transformer.from_crs("EPSG:4326", loc.get("projParameter"), always_xy=True)

        def to_xy(geom):                                   # lon/lat -> the network's x/y in metres
            def convert(c):
                x, y = proj.transform(c[:, 0], c[:, 1])
                return np.column_stack([x + ox, y + oy])
            return shapely.transform(geom, convert)

        # 2. the three barangays
        gj = json.loads((thesis / "data" / "santa_rosa_barangays.geojson").read_text(encoding="utf-8"))
        features = [f for f in gj["features"] if f["properties"].get("adm4_pcode") in BARANGAYS]
        if len(features) != len(BARANGAYS):
            raise SystemExit("Not every barangay of BARANGAYS is in the boundary file")
        GEOJSON.parent.mkdir(exist_ok=True)
        GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
                           encoding="utf-8")
        polys = {BARANGAYS[f["properties"]["adm4_pcode"]]: to_xy(shape(f["geometry"])) for f in features}
        area = unary_union(list(polys.values())).buffer(EDGE_TOLERANCE_M)

        # 3. the jeepney roads: every edge a thesis line drives, and the other direction of it
        lines = json.loads((thesis / "generated" / "jeepney_routes.json").read_text(encoding="utf-8"))
        nodes = {n.get("id"): n for n in nod.getroot().iter("node")}
        edges = {e.get("id"): e for e in edg.getroot().iter("edge")}
        jeepney_edges = {eid for r in lines.values() for eid in r["edges"]}
        candidates = jeepney_edges | {twin(e) for e in jeepney_edges if twin(e) in edges}

        def geometry(e):
            s = e.get("shape")
            if s:
                return LineString([tuple(map(float, p.split(",")[:2])) for p in s.split()])
            a, b = nodes[e.get("from")], nodes[e.get("to")]
            return LineString([(float(a.get("x")), float(a.get("y"))), (float(b.get("x")), float(b.get("y")))])

        # 4. cut them where they leave the area; a cut gets a new node, shared by both directions
        cut_nodes = []                                       # [(id, x, y)]

        def cut_node(x, y):
            for nid, cx, cy in cut_nodes:
                if (cx - x) ** 2 + (cy - y) ** 2 < 1.0:
                    return nid
            nid = f"cut_{len(cut_nodes)}"
            cut_nodes.append((nid, x, y))
            return nid

        pieces = {}                                          # old edge id -> [(new id, from, to, coords|None)]
        for eid in sorted(candidates):
            e = edges[eid]
            line = geometry(e)
            parts = pieces_of(line, area)
            if not parts:
                continue
            if len(parts) == 1 and line.length - parts[0].length < 0.5:
                pieces[eid] = [(eid, e.get("from"), e.get("to"), None)]       # wholly inside: unchanged
                continue
            out = []
            for k, p in enumerate(parts):
                start, end = p.coords[0], p.coords[-1]
                a = e.get("from") if line.project(Point(start)) < 0.5 else cut_node(*start)
                b = e.get("to") if line.length - line.project(Point(end)) < 0.5 else cut_node(*end)
                out.append((eid if len(parts) == 1 else f"{eid}_{k}", a, b, list(p.coords)))
            pieces[eid] = out
        kept = {new: old for old, ps in pieces.items() for new, *_ in ps}
        split = {old for old, ps in pieces.items() if len(ps) > 1}

        # 5. plain XML of the cut network
        n_root = ET.Element("nodes")
        n_root.append(loc)
        used = {p[i] for ps in pieces.values() for p in ps for i in (1, 2)}
        for nid in sorted(used):
            if nid in nodes:
                n_root.append(nodes[nid])
        for nid, x, y in cut_nodes:
            ET.SubElement(n_root, "node", id=nid, x=f"{x:.2f}", y=f"{y:.2f}", type="priority", fringe="outer")
        ET.ElementTree(n_root).write(tmp / "cut.nod.xml", encoding="UTF-8", xml_declaration=True)

        e_root = ET.Element("edges")
        for old, ps in pieces.items():
            for new, a, b, coords in ps:
                e = ET.fromstring(ET.tostring(edges[old]))
                e.set("id", new)
                e.set("from", a)
                e.set("to", b)
                if coords is not None:                     # cut: new shape, length from it
                    e.set("shape", fmt(coords))
                    e.attrib.pop("length", None)
                for lane in e.iter("lane"):
                    for neigh in list(lane.findall("neigh")):
                        other = neigh.get("lane").rsplit("_", 1)[0]
                        if other not in kept or other in split or old in split:
                            lane.remove(neigh)
                e_root.append(e)
        for rb in edg.getroot().iter("roundabout"):
            if set(rb.get("edges").split()) <= set(kept) - split:
                e_root.append(rb)
        ET.ElementTree(e_root).write(tmp / "cut.edg.xml", encoding="UTF-8", xml_declaration=True)

        # the thesis's turning lanes where both roads are kept and meet at the same junction
        c_root = ET.Element("connections")
        for c in con.getroot().iter("connection"):
            f, t = c.get("from"), c.get("to")
            if f not in pieces or t not in pieces:
                continue
            last, first = pieces[f][-1], pieces[t][0]
            if last[2] == edges[f].get("to") and first[1] == edges[t].get("from") and last[2] == first[1]:
                c.set("from", last[0])
                c.set("to", first[0])
                c_root.append(c)
        ET.ElementTree(c_root).write(tmp / "cut.con.xml", encoding="UTF-8", xml_declaration=True)

        NET.parent.mkdir(exist_ok=True)
        subprocess.run([netconvert(), "--node-files", str(tmp / "cut.nod.xml"), "--edge-files", str(tmp / "cut.edg.xml"),
                        "--connection-files", str(tmp / "cut.con.xml"), "--type-files", str(tmp / "bayan.typ.xml"),
                        "--output-file", str(NET), "--output.street-names", "--crossings.guess",
                        "--offset.disable-normalization",          # the thesis network's x/y, so both line up
                        "--no-warnings"], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 6. the jeepney lines on the cut network: each line's edges that are kept, in order, split where
    # consecutive edges do not join (a line that leaves the three barangays and comes back)
    import sumolib
    net = sumolib.net.readNet(str(NET))

    def joined(a, b):
        return any(c.getFromLane().allows("bus") and c.getToLane().allows("bus")
                   for c in net.getEdge(a).getOutgoing().get(net.getEdge(b), []))

    routes = {}
    for name, r in lines.items():
        seq = [new for old in r["edges"] if old in pieces for new, *_ in pieces[old]]
        runs = []
        for eid in seq:
            if runs and joined(runs[-1][-1], eid):
                runs[-1].append(eid)
            else:
                runs.append([eid])
        runs = [run for run in runs if sum(net.getEdge(e).getLength() for e in run) >= 100]
        for k, run in enumerate(runs):
            routes[name if len(runs) == 1 else f"{name}_{k + 1}"] = (r["highway"], run)

    vtype = next(v for v in ET.parse(thesis / "generated" / "vtypes.add.xml").getroot().iter("vType")
                 if v.get("id") == "jeepney")
    ROUTES.parent.mkdir(exist_ok=True)
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           "<!-- Generated by tools/build_from_thesis.py: the thesis's jeepney type and lines, cut to Macabling,",
           f"     Pooc and Balibago. One jeepney per line every {HEADWAY_S} s, entering at full speed. -->",
           "<routes>",
           "    " + ET.tostring(vtype, encoding="unicode").strip()]
    for name, (road, run) in routes.items():
        km = sum(net.getEdge(e).getLength() for e in run) / 1000
        xml.append(f'    <!-- {name}: {road}, {km:.2f} km -->')
        xml.append(f'    <route id="r_{name}" edges="{" ".join(run)}"/>')
    for name in routes:
        xml.append(f'    <flow id="{name}" type="jeepney" route="r_{name}" line="{name}" begin="0" end="{END_S}" '
                   f'period="{HEADWAY_S}" departLane="best" departSpeed="max"/>')
    xml.append("</routes>")
    ROUTES.write_text("\n".join(xml) + "\n", encoding="utf-8")

    # 7. the barangay outlines for sumo-gui, and the simulation
    poly = ['<?xml version="1.0" encoding="UTF-8"?>', "<!-- Generated by tools/build_from_thesis.py -->", "<additional>"]
    for f in features:
        name = BARANGAYS[f["properties"]["adm4_pcode"]]
        g = shape(f["geometry"])
        for k, p in enumerate(getattr(g, "geoms", [g])):
            ring = " ".join(f"{x:.6f},{y:.6f}" for x, y in p.exterior.coords)
            poly.append(f'    <poly id="{name}{"_" + str(k) if k else ""}" type="barangay {name}" color="{COLORS[name]}" '
                        f'fill="0" lineWidth="3" layer="-1" geo="1" shape="{ring}"/>')
    poly.append("</additional>")
    POLY.write_text("\n".join(poly) + "\n", encoding="utf-8")

    CONFIG.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by tools/build_from_thesis.py. sumo-gui -c jeepney.sumocfg -->
<configuration>
    <input>
        <net-file value="network/santarosa_3brgy.net.xml"/>
        <route-files value="demand/jeepneys.rou.xml,demand/traffic.rou.xml,demand/passengers.rou.xml"/>
        <additional-files value="network/barangays.poly.xml,network/jeepney_stops.add.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="{END_S}"/>
        <step-length value="1"/>
    </time>
    <processing>
        <!-- as in the thesis: sublanes, so motorcycles can filter past jeepneys -->
        <lateral-resolution value="0.4"/>
        <time-to-teleport value="-1"/>
        <collision.action value="warn"/>
    </processing>
    <random_number>
        <seed value="42"/>
    </random_number>
</configuration>
""", encoding="utf-8")

    # 8. what was kept
    per = {}
    for e in net.getEdges():                               # each direction counts half: km of road
        share = 0.5 if net.hasEdge(twin(e.getID())) else 1.0
        per[e.getName() or "(no name)"] = per.get(e.getName() or "(no name)", 0) + share * e.getLength()
    tls = [n for n in net.getNodes() if n.getType() == "traffic_light"]
    print(f"\nWrote {NET.relative_to(HERE)}: {len(kept)} edges, {len(cut_nodes)} cut points, "
          f"{len(tls)} traffic lights")
    print("  " + ", ".join(f"{n} {m / 1000:.2f} km" for n, m in sorted(per.items(), key=lambda x: -x[1])))
    print(f"Wrote {ROUTES.relative_to(HERE)}: {len(routes)} lines")
    for name, (road, run) in routes.items():
        print(f"  {name:12s} {road}: {sum(net.getEdge(e).getLength() for e in run) / 1000:.2f} km, {len(run)} edges")


if __name__ == "__main__":
    main()
