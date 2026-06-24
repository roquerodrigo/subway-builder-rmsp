#!/usr/bin/env python3
"""ocean_depth_index.json.gz — OSM water bodies -> grid-indexed depth format.

RMSP has no ocean; this captures reservoirs (Billings, Guarapiranga) and rivers
(Tietê, Pinheiros) so the game treats them as water. Mirrors shipped format:
{cs, bbox, grid, cells:[[gx,gy,idx...]], depths:[{b, d, p}], stats}. d is a
negative depth in metres.
"""
import json, gzip, os, math
import config
from lib_geojsonseq import read_features, outer_rings

SRC = os.path.join(config.SOURCES, "water.geojsonseq")
OUT = os.path.join(config.OUT, "ocean_depth_index.json")
CS = config.CELL_SIZE


def ring_area_deg(ring):
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]; x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def main():
    depths = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for ft in read_features(SRC):
        geom = ft.get("geometry") or {}
        for ring in outer_rings(geom):
            if len(ring) < 4:
                continue
            xs = [c[0] for c in ring]; ys = [c[1] for c in ring]
            bx = [min(xs), min(ys), max(xs), max(ys)]
            if bx[2] < config.MIN_LNG or bx[0] > config.MAX_LNG:
                continue
            if bx[3] < config.MIN_LAT or bx[1] > config.MAX_LAT:
                continue
            # bigger water bodies (reservoirs) are deeper than narrow rivers
            d = -10 if ring_area_deg(ring) > 1e-5 else -4
            p = [[round(c[0], 6), round(c[1], 6)] for c in ring]
            depths.append({"b": [round(v, 6) for v in bx], "d": d, "p": p})
            minx = min(minx, bx[0]); miny = min(miny, bx[1])
            maxx = max(maxx, bx[2]); maxy = max(maxy, bx[3])

    if not depths:
        # produce a valid empty index covering the city bbox
        out_obj = {"cs": CS, "bbox": config.BBOX, "grid": [1, 1],
                   "cells": [], "depths": [], "stats": {"count": 0, "maxDepth": 0}}
    else:
        gw = max(1, int(math.ceil((maxx - minx) / CS)))
        gh = max(1, int(math.ceil((maxy - miny) / CS)))
        cells = {}
        for i, w in enumerate(depths):
            gx0 = int((w["b"][0] - minx) / CS); gx1 = int((w["b"][2] - minx) / CS)
            gy0 = int((w["b"][1] - miny) / CS); gy1 = int((w["b"][3] - miny) / CS)
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    cells.setdefault((gx, gy), []).append(i)
        cell_list = [[gx, gy] + idxs for (gx, gy), idxs in cells.items()]
        out_obj = {
            "cs": CS,
            "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
            "grid": [gw, gh],
            "cells": cell_list,
            "depths": depths,
            "stats": {"count": len(depths),
                      "maxDepth": min((w["d"] for w in depths), default=0)},
        }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(out_obj, f, separators=(",", ":"))
    print(f"water bodies={len(depths)} -> {OUT}.gz "
          f"({os.path.getsize(OUT + '.gz')/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
