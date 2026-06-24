#!/usr/bin/env python3
"""runways_taxiways.geojson.gz — OSM aeroway -> MultiPolygon surfaces.

Runways/taxiways are usually OSM LineStrings; we buffer them by half their width
(reprojected to metres) into surfaces. Aprons/aerodrome areas are kept as-is.
Covers Congonhas (CGH), Guarulhos (GRU) and Campo de Marte, all within the bbox.
"""
import json, gzip, os
import config
from lib_geojsonseq import read_features, outer_rings
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

SRC = os.path.join(config.SOURCES, "aero.geojsonseq")
OUT = os.path.join(config.OUT, "runways_taxiways.geojson")

# Corrego Alegre / UTM-ish metres for buffering (any local metric CRS is fine).
TO_M = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True).transform
TO_DEG = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True).transform

HALF_WIDTH = {"runway": 25.0, "taxiway": 12.0, "apron": 0.0}


def in_bbox_coords(coords):
    for lng, lat in coords:
        if config.in_bbox(lng, lat):
            return True
    return False


def main():
    polys_m = []
    for ft in read_features(SRC):
        geom = ft.get("geometry") or {}
        props = ft.get("properties") or {}
        kind = props.get("aeroway") or ""
        t = geom.get("type")
        if t == "LineString":
            coords = geom.get("coordinates") or []
            if len(coords) < 2 or not in_bbox_coords(coords):
                continue
            hw = HALF_WIDTH.get(kind, 10.0)
            line_m = shp_transform(TO_M, LineString(coords))
            polys_m.append(line_m.buffer(max(hw, 6.0), cap_style=2, join_style=2))
        elif t in ("Polygon", "MultiPolygon"):
            for ring in outer_rings(geom):
                if len(ring) < 4 or not in_bbox_coords(ring):
                    continue
                if kind == "aerodrome":
                    continue  # skip whole-airport boundary; keep runway/taxiway/apron
                polys_m.append(shp_transform(TO_M, Polygon(ring)))

    if not polys_m:
        fc = {"type": "FeatureCollection", "features": []}
    else:
        merged = unary_union(polys_m)
        merged_deg = shp_transform(TO_DEG, merged)
        geoms = merged_deg.geoms if merged_deg.geom_type == "MultiPolygon" else [merged_deg]
        feats = []
        for g in geoms:
            mp = {"type": "MultiPolygon", "coordinates": [
                [[[round(x, 6), round(y, 6)] for x, y in g.exterior.coords]] ]}
            feats.append({"type": "Feature", "geometry": mp, "properties": {}})
        fc = {"type": "FeatureCollection", "features": feats}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"airport surfaces={len(fc['features'])} -> {OUT}.gz "
          f"({os.path.getsize(OUT + '.gz')/1e3:.0f} KB)")


if __name__ == "__main__":
    main()
