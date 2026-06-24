"""Turn the OSM GeoJSONSeq subsets into the game's data files:
roads.geojson.gz, buildings_index.json.gz, ocean_depth_index.json.gz,
runways_taxiways.geojson.gz."""

from __future__ import annotations

import logging
import math
from collections import Counter

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

_HIGHWAY = {"motorway", "motorway_link", "trunk", "trunk_link"}
_MAJOR = {"primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link"}


def road_class(highway: str) -> str:
    """Map an OSM highway tag to the game's {highway, major, minor} classes."""
    if highway in _HIGHWAY:
        return "highway"
    if highway in _MAJOR:
        return "major"
    return "minor"


def ring_area_m2(ring: list[list[float]]) -> float:
    """Approximate polygon-ring area in m² (shoelace × local degree scale)."""
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 * settings.m_per_deg_lat * settings.m_per_deg_lng


def ring_area_deg2(ring: list[list[float]]) -> float:
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _ring_in_bbox(bx: list[float]) -> bool:
    """Does a [minLng,minLat,maxLng,maxLat] bbox intersect the city bbox?"""
    return not (
        bx[2] < settings.min_lng
        or bx[0] > settings.max_lng
        or bx[3] < settings.min_lat
        or bx[1] > settings.max_lat
    )


def _coords_in_bbox(coords: list[list[float]]) -> bool:
    return any(settings.in_bbox(lng, lat) for lng, lat in coords)


# --------------------------------------------------------------------------- roads
def build_roads() -> None:
    out = settings.build_dir / "roads.geojson.gz"
    feats = []
    for ft in geojson.read_features(settings.sources_dir / "roads.geojsonseq"):
        geom = ft.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2 or not _coords_in_bbox(coords):
            continue
        props = ft.get("properties") or {}
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(c[0], 6), round(c[1], 6)] for c in coords],
                },
                "properties": {
                    "roadClass": road_class(props.get("highway") or ""),
                    "structure": "normal",
                    "name": props.get("name") or "",
                },
            }
        )
    geojson.write_json_gz({"type": "FeatureCollection", "features": feats}, out)
    classes = Counter(f["properties"]["roadClass"] for f in feats)
    log.info("roads=%d %s -> %s (%.1f MB)", len(feats), dict(classes), out.name, geojson.mb(out))


# ----------------------------------------------------------------------- buildings
def _floors(props: dict) -> int:
    try:
        return max(
            1, min(int(round(float(props.get("building:levels")))), settings.bldg_max_floors)
        )
    except (TypeError, ValueError):
        return 1


def _simplify_ring(ring: list[list[float]]) -> list[list[float]]:
    if len(ring) <= 6:
        return ring
    try:
        from shapely.geometry import Polygon

        p = Polygon(ring).simplify(settings.bldg_simplify_tol, preserve_topology=False)
        if p.is_empty or p.geom_type != "Polygon":
            return ring
        c = list(p.exterior.coords)
        return c if len(c) >= 4 else ring
    except Exception:
        return ring


def build_buildings() -> None:
    out = settings.build_dir / "buildings_index.json.gz"
    cs = settings.cell_size
    dec = settings.bldg_decimals
    buildings: list[dict] = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for ft in geojson.read_features(settings.sources_dir / "buildings.geojsonseq"):
        geom = ft.get("geometry") or {}
        for ring in geojson.outer_rings(geom):
            if len(ring) < 4:
                continue
            bx = [
                min(c[0] for c in ring),
                min(c[1] for c in ring),
                max(c[0] for c in ring),
                max(c[1] for c in ring),
            ]
            if not _ring_in_bbox(bx) or ring_area_m2(ring) < settings.bldg_area_min_m2:
                continue
            f = _floors(ft.get("properties") or {})
            p = [[round(c[0], dec), round(c[1], dec)] for c in _simplify_ring(ring)]
            bx = [
                min(c[0] for c in p),
                min(c[1] for c in p),
                max(c[0] for c in p),
                max(c[1] for c in p),
            ]
            buildings.append({"b": [round(v, dec) for v in bx], "f": f, "p": p})
            minx, miny = min(minx, bx[0]), min(miny, bx[1])
            maxx, maxy = max(maxx, bx[2]), max(maxy, bx[3])

    if not buildings:
        raise RuntimeError("no buildings in bbox")

    cells = _grid_cells(buildings, minx, miny, cs)
    gw = max(1, math.ceil((maxx - minx) / cs))
    gh = max(1, math.ceil((maxy - miny) / cs))
    geojson.write_json_gz(
        {
            "cs": cs,
            "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
            "grid": [gw, gh],
            "cells": cells,
            "buildings": buildings,
            "stats": {"count": len(buildings), "maxDepth": max(b["f"] for b in buildings)},
        },
        out,
    )
    log.info(
        "buildings=%d grid=%dx%d cells=%d -> %s (%.1f MB)",
        len(buildings),
        gw,
        gh,
        len(cells),
        out.name,
        geojson.mb(out),
    )


def _grid_cells(items: list[dict], minx: float, miny: float, cs: float) -> list[list[int]]:
    """Assign each item (with bbox key 'b') to every grid cell its bbox touches."""
    cells: dict[tuple[int, int], list[int]] = {}
    for i, it in enumerate(items):
        b = it["b"]
        gx0, gx1 = int((b[0] - minx) / cs), int((b[2] - minx) / cs)
        gy0, gy1 = int((b[1] - miny) / cs), int((b[3] - miny) / cs)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                cells.setdefault((gx, gy), []).append(i)
    return [[gx, gy, *idxs] for (gx, gy), idxs in cells.items()]


# --------------------------------------------------------------------------- water
def build_water() -> None:
    out = settings.build_dir / "ocean_depth_index.json.gz"
    cs = settings.cell_size
    depths: list[dict] = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for ft in geojson.read_features(settings.sources_dir / "water.geojsonseq"):
        for ring in geojson.outer_rings(ft.get("geometry") or {}):
            if len(ring) < 4:
                continue
            bx = [
                min(c[0] for c in ring),
                min(c[1] for c in ring),
                max(c[0] for c in ring),
                max(c[1] for c in ring),
            ]
            if not _ring_in_bbox(bx):
                continue
            d = (
                settings.water_deep_depth
                if ring_area_deg2(ring) > settings.water_deep_area_deg2
                else settings.water_shallow_depth
            )
            p = [[round(c[0], 6), round(c[1], 6)] for c in ring]
            depths.append({"b": [round(v, 6) for v in bx], "d": d, "p": p})
            minx, miny = min(minx, bx[0]), min(miny, bx[1])
            maxx, maxy = max(maxx, bx[2]), max(maxy, bx[3])

    if not depths:
        obj = {
            "cs": cs,
            "bbox": list(settings.bbox),
            "grid": [1, 1],
            "cells": [],
            "depths": [],
            "stats": {"count": 0, "maxDepth": 0},
        }
    else:
        cells = _grid_cells(depths, minx, miny, cs)
        gw = max(1, math.ceil((maxx - minx) / cs))
        gh = max(1, math.ceil((maxy - miny) / cs))
        obj = {
            "cs": cs,
            "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
            "grid": [gw, gh],
            "cells": cells,
            "depths": depths,
            "stats": {"count": len(depths), "maxDepth": min(d["d"] for d in depths)},
        }
    geojson.write_json_gz(obj, out)
    log.info("water bodies=%d -> %s (%.2f MB)", len(depths), out.name, geojson.mb(out))


# ------------------------------------------------------------------------ airports
def build_airports() -> None:
    out = settings.build_dir / "runways_taxiways.geojson.gz"
    from pyproj import Transformer
    from shapely.geometry import LineString, Polygon
    from shapely.ops import transform as shp_transform
    from shapely.ops import unary_union

    to_m = Transformer.from_crs("EPSG:4326", settings.metric_crs, always_xy=True).transform
    to_deg = Transformer.from_crs(settings.metric_crs, "EPSG:4326", always_xy=True).transform

    polys_m = []
    for ft in geojson.read_features(settings.sources_dir / "aero.geojsonseq"):
        geom = ft.get("geometry") or {}
        kind = (ft.get("properties") or {}).get("aeroway") or ""
        t = geom.get("type")
        if t == "LineString":
            coords = geom.get("coordinates") or []
            if len(coords) < 2 or not _coords_in_bbox(coords):
                continue
            hw = settings.airport_half_width.get(kind, settings.airport_default_half_width)
            line_m = shp_transform(to_m, LineString(coords))
            polys_m.append(
                line_m.buffer(max(hw, settings.airport_min_buffer), cap_style=2, join_style=2)
            )
        elif t in ("Polygon", "MultiPolygon"):
            for ring in geojson.outer_rings(geom):
                if len(ring) < 4 or not _coords_in_bbox(ring) or kind == "aerodrome":
                    continue
                polys_m.append(shp_transform(to_m, Polygon(ring)))

    feats = []
    if polys_m:
        merged = shp_transform(to_deg, unary_union(polys_m))
        geoms = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
        feats = [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[round(x, 6), round(y, 6)] for x, y in g.exterior.coords]]],
                },
            }
            for g in geoms
        ]
    geojson.write_json_gz({"type": "FeatureCollection", "features": feats}, out)
    log.info("airport surfaces=%d -> %s (%.0f KB)", len(feats), out.name, geojson.mb(out) * 1000)


def build_all() -> None:
    settings.ensure_dirs()
    build_roads()
    build_buildings()
    build_water()
    build_airports()
