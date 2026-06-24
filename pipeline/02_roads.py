#!/usr/bin/env python3
"""roads.geojson.gz — OSM highways -> Subway Builder roads format.

Output: FeatureCollection of LineString with properties {roadClass, structure, name}.
roadClass mirrors shipped cities: one of {highway, major, minor}. structure is
always "normal" (shipped data never uses bridge/tunnel here).
"""
import json, gzip, os
import config
from lib_geojsonseq import read_features

SRC = os.path.join(config.SOURCES, "roads.geojsonseq")
OUT = os.path.join(config.OUT, "roads.geojson")

HIGHWAY = {"motorway", "motorway_link", "trunk", "trunk_link"}
MAJOR = {"primary", "primary_link", "secondary", "secondary_link",
         "tertiary", "tertiary_link"}


def road_class(hw):
    if hw in HIGHWAY:
        return "highway"
    if hw in MAJOR:
        return "major"
    return "minor"


def any_in_bbox(coords):
    for lng, lat in coords:
        if config.in_bbox(lng, lat):
            return True
    return False


def main():
    out_feats = []
    kept = skipped = 0
    for ft in read_features(SRC):
        geom = ft.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2 or not any_in_bbox(coords):
            skipped += 1
            continue
        props = ft.get("properties") or {}
        hw = props.get("highway") or ""
        out_feats.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(c[0], 6), round(c[1], 6)] for c in coords],
            },
            "properties": {
                "roadClass": road_class(hw),
                "structure": "normal",
                "name": props.get("name") or "",
            },
        })
        kept += 1

    fc = {"type": "FeatureCollection", "features": out_feats}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    rc = Counter(ft["properties"]["roadClass"] for ft in out_feats)
    print(f"roads kept={kept} skipped={skipped} classes={dict(rc)}")
    print(f"  -> {OUT}.gz ({os.path.getsize(OUT + '.gz')/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
