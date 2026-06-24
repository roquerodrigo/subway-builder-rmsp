#!/usr/bin/env python3
"""buildings_index.json.gz — OSM building footprints -> grid-indexed format.

Matches shipped cities: {cs, bbox, grid:[nx,ny], cells:[[gx,gy,idx...]],
buildings:[{b:[minLng,minLat,maxLng,maxLat], f:floors, p:[[lng,lat]...]}], stats}.
'f' is the number of floors (positive int, default 1).
"""
import json, gzip, os, math
import config
from lib_geojsonseq import read_features, outer_rings
from shapely.geometry import Polygon

SRC = os.path.join(config.SOURCES, "buildings.geojsonseq")
OUT = os.path.join(config.OUT, "buildings_index.json")
CS = config.CELL_SIZE

# Trim to keep the file in the same scale as shipped cities (SF ~1.2M/45MB):
# drop tiny footprints (sheds/garages) and simplify redundant vertices.
AREA_MIN_M2 = 30.0
SIMPLIFY_TOL = 9.0e-6           # ~1 m in degrees
M_PER_DEG_LAT = 110900.0
M_PER_DEG_LNG = 101900.0        # at ~lat -23.5


def floors(props):
    v = props.get("building:levels")
    try:
        n = int(round(float(v)))
        return max(1, min(n, 80))
    except (TypeError, ValueError):
        return 1


def area_m2(ring):
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]; x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 * M_PER_DEG_LAT * M_PER_DEG_LNG


def simplify(ring):
    if len(ring) <= 6:
        return ring
    try:
        p = Polygon(ring).simplify(SIMPLIFY_TOL, preserve_topology=False)
        if p.is_empty or p.geom_type != "Polygon":
            return ring
        c = list(p.exterior.coords)
        return c if len(c) >= 4 else ring
    except Exception:
        return ring


def main():
    buildings = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    seen = 0
    for ft in read_features(SRC):
        geom = ft.get("geometry") or {}
        for ring in outer_rings(geom):
            if len(ring) < 4:
                continue
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            bx = [min(xs), min(ys), max(xs), max(ys)]
            # keep if footprint bbox intersects the city bbox
            if bx[2] < config.MIN_LNG or bx[0] > config.MAX_LNG:
                continue
            if bx[3] < config.MIN_LAT or bx[1] > config.MAX_LAT:
                continue
            if area_m2(ring) < AREA_MIN_M2:
                continue
            seen += 1
            f = floors(ft.get("properties") or {})
            ring = simplify(ring)
            p = [[round(c[0], 5), round(c[1], 5)] for c in ring]
            xs = [c[0] for c in p]; ys = [c[1] for c in p]
            bx = [min(xs), min(ys), max(xs), max(ys)]
            buildings.append({"b": [round(v, 5) for v in bx], "f": f, "p": p})
            minx = min(minx, bx[0]); miny = min(miny, bx[1])
            maxx = max(maxx, bx[2]); maxy = max(maxy, bx[3])

    if not buildings:
        raise SystemExit("no buildings in bbox")

    gw = max(1, int(math.ceil((maxx - minx) / CS)))
    gh = max(1, int(math.ceil((maxy - miny) / CS)))
    cells = {}
    for i, b in enumerate(buildings):
        # assign every grid cell the footprint bbox touches
        gx0 = int((b["b"][0] - minx) / CS); gx1 = int((b["b"][2] - minx) / CS)
        gy0 = int((b["b"][1] - miny) / CS); gy1 = int((b["b"][3] - miny) / CS)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                cells.setdefault((gx, gy), []).append(i)
    cell_list = [[gx, gy] + idxs for (gx, gy), idxs in cells.items()]

    out_obj = {
        "cs": CS,
        "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
        "grid": [gw, gh],
        "cells": cell_list,
        "buildings": buildings,
        "stats": {"count": len(buildings),
                  "maxDepth": max((b["f"] for b in buildings), default=1)},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(out_obj, f, separators=(",", ":"))
    print(f"buildings={len(buildings)} grid={gw}x{gh} cells={len(cell_list)}")
    print(f"  -> {OUT}.gz ({os.path.getsize(OUT + '.gz')/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
