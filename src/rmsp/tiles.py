"""Vector basemap: build PMTiles from the OSM subsets (tippecanoe) and serve them.

Layer names match the game's style so it renders water/parks/buildings/airports:
  - RMSP.pmtiles            -> water, parks, airports, buildings
  - RMSP_foundations.pmtiles -> foundations (buildings), ocean_foundations (water)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from rmsp import external, geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

# layers that go straight to NDJSON (just strip osmium's RS byte). Everything else
# is enriched with the property its style layer reads (area/height/depth_min/name).
_PLAIN_NDJSON = ["aero"]

# place=* OSM classes -> the game's three label source-layers (text-field = name)
_LABEL_CLASSES = {
    "city_labels": {"city", "town"},
    "suburb_labels": {"suburb", "borough"},
    "neighborhood_labels": {"neighbourhood", "quarter", "hamlet", "village"},
}


def _to_ndjson() -> None:
    """Strip the RS (0x1e) byte osmium prefixes so tippecanoe reads plain NDJSON."""
    for stem in _PLAIN_NDJSON:
        src = settings.sources_dir / f"{stem}.geojsonseq"
        dst = settings.sources_dir / f"{stem}.ndjson"
        dst.write_bytes(src.read_bytes().replace(b"\x1e", b""))


def _to_metric():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", settings.metric_crs, always_xy=True).transform


def _write_ndjson(stem: str, features) -> int:
    n = 0
    with open(settings.sources_dir / f"{stem}.ndjson", "w", encoding="utf-8") as out:
        for ft in features:
            out.write(json.dumps(ft, separators=(",", ":")) + "\n")
            n += 1
    return n


def _polygonal(g):
    """Keep only the polygonal part of a geometry (difference can yield collections)."""
    if g.is_empty:
        return g
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    from shapely.ops import unary_union

    parts = [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else g


def _load_polys(stem):
    """Load valid Polygon/MultiPolygon geometries from a <stem>.geojsonseq."""
    from shapely.geometry import shape

    out = []
    for ft in geojson.read_features(settings.sources_dir / f"{stem}.geojsonseq"):
        geom = ft.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
            g = g if g.is_valid else g.buffer(0)
            if not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon"):
                out.append(g)
        except Exception:
            continue
    return out


def _parks_ndjson() -> None:
    """parks.ndjson with an `area` (m²) property (the style's parks-large/-small filter
    on `["get","area"]` ≥/< 1e5, so without it no green renders).

    Parks are **dissolved** (unary_union) so nested/overlapping green features — a park
    inside a park, e.g. Ibirapuera's inner lawns/fields — merge into a single fill instead
    of z-fighting at the same elevation. **Water and airport surfaces are then subtracted**,
    so a lake inside a park, or the grass over an aerodrome/apron (e.g. GRU), becomes a hole
    and renders from its own layer rather than blending with the green at the same z."""
    from shapely.geometry import mapping
    from shapely.ops import transform, unary_union

    to_m = _to_metric()
    merged = unary_union(_load_polys("parks"))
    # carve out water bodies and airport footprints (aerodrome/apron polygons)
    exclude = unary_union(_load_polys("water") + _load_polys("aero"))
    if not exclude.is_empty:
        merged = _polygonal(merged.difference(exclude))

    def feats():
        geoms = merged.geoms if merged.geom_type == "MultiPolygon" else [merged]
        for g in geoms:
            if g.is_empty:
                continue
            yield {
                "type": "Feature",
                "geometry": mapping(g),
                "properties": {"area": round(transform(to_m, g).area)},  # style reads area
            }

    log.info("parks dissolved + water/airport subtracted: %d", _write_ndjson("parks", feats()))


def _bldg_height(props: dict) -> float | None:
    """Building height in metres from OSM tags (`height`, else `building:levels`×3.2)."""
    h = props.get("height")
    if h:
        try:
            return round(float(str(h).split(";")[0].replace("m", "").strip()), 1)
        except ValueError:
            pass
    lv = props.get("building:levels")
    if lv:
        try:
            return round(float(str(lv).split(";")[0].strip()) * 3.2, 1)
        except ValueError:
            pass
    return None


def _buildings_ndjson() -> None:
    """buildings.ndjson feeding two style layers: the basemap `buildings` extrusion reads
    `["get","height"]` (m) and the foundations-view `foundations` layer reads
    `["get","foundationDepth"]` (basement levels). Both have a fallback, so each property
    is only emitted when it carries real information (height present / depth > 1)."""
    from rmsp.layers import foundation_depth

    def feats():
        for ft in geojson.read_features(settings.sources_dir / "buildings.geojsonseq"):
            if not ft.get("geometry"):
                continue
            props = ft.get("properties") or {}
            out: dict = {}
            height = _bldg_height(props)
            if height:
                out["height"] = height
            depth = foundation_depth(props)
            if depth > 1:
                out["foundationDepth"] = depth
            ft["properties"] = out
            yield ft

    log.info("buildings: %d -> buildings.ndjson", _write_ndjson("buildings", feats()))


def _water_ndjson() -> None:
    """water.ndjson with a `depth_min` (negative m) property. The basemap `water` fill
    ignores it, but the foundations-view `ocean_foundations` layer colours and labels
    water by `["get","depth_min"]`; without it those labels read "undefined"."""
    from shapely.geometry import shape
    from shapely.ops import transform

    to_m = _to_metric()
    deep_m2 = settings.water_deep_area_deg2 * settings.m_per_deg_lat * settings.m_per_deg_lng

    def feats():
        for ft in geojson.read_features(settings.sources_dir / "water.geojsonseq"):
            geom = ft.get("geometry")
            if not geom:
                continue
            try:
                area = transform(to_m, shape(geom)).area
            except Exception:
                area = 0
            depth = settings.water_deep_depth if area >= deep_m2 else settings.water_shallow_depth
            ft["properties"] = {"depth_min": depth}
            yield ft

    log.info("water with depth_min: %d -> water.ndjson", _write_ndjson("water", feats()))


def _places_ndjson() -> None:
    """Split OSM place=* points into the game's three label layers (city/suburb/
    neighborhood), each carrying just `name` (the only property the style reads)."""
    buckets: dict[str, list] = {k: [] for k in _LABEL_CLASSES}
    for ft in geojson.read_features(settings.sources_dir / "places.geojsonseq"):
        props = ft.get("properties") or {}
        name = props.get("name")
        place = props.get("place")
        if not name or not ft.get("geometry"):
            continue
        for layer, classes in _LABEL_CLASSES.items():
            if place in classes:
                buckets[layer].append({**ft, "properties": {"name": name}})
                break
    for layer, fts in buckets.items():
        n = _write_ndjson(layer, iter(fts))
        log.info("%s: %d labels", layer, n)


def _nd(stem: str) -> Path:
    return settings.sources_dir / f"{stem}.ndjson"


def build_tiles() -> None:
    settings.ensure_dirs()
    _to_ndjson()
    _parks_ndjson()
    _buildings_ndjson()
    _water_ndjson()
    _places_ndjson()
    basemap = settings.tiles_dir / "RMSP.pmtiles"
    foundations = settings.tiles_dir / "RMSP_foundations.pmtiles"

    log.info("building basemap tiles -> %s", basemap.name)
    external.run(
        [
            "tippecanoe",
            "-o",
            basemap,
            "--force",
            "-Z",
            str(settings.tile_zoom_min),
            "-z",
            str(settings.tile_zoom_max),
            "-L",
            f"water:{_nd('water')}",
            "-L",
            f"parks:{_nd('parks')}",
            "-L",
            f"airports:{_nd('aero')}",
            "-L",
            f"buildings:{_nd('buildings')}",
            "-L",
            f"city_labels:{_nd('city_labels')}",
            "-L",
            f"suburb_labels:{_nd('suburb_labels')}",
            "-L",
            f"neighborhood_labels:{_nd('neighborhood_labels')}",
            "--drop-densest-as-needed",
            "--coalesce-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            # the park hole (water subtracted) and the water polygon share an identical
            # border; make tippecanoe simplify it the same on both so the lake shoreline
            # doesn't gap/z-fight at low zoom.
            "--detect-shared-borders",
            "--no-simplification-of-shared-nodes",
            "--no-tile-size-limit",
        ]
    )

    log.info("building foundation tiles -> %s", foundations.name)
    external.run(
        [
            "tippecanoe",
            "-o",
            foundations,
            "--force",
            "-Z",
            str(settings.foundation_zoom_min),
            "-z",
            str(settings.tile_zoom_max),
            "-L",
            f"foundations:{_nd('buildings')}",
            "-L",
            f"ocean_foundations:{_nd('water')}",
            "--drop-densest-as-needed",
            "--no-tile-size-limit",
        ]
    )


def serve_tiles() -> None:
    """Serve the tiles (blocking). The mod auto-detects this on http://127.0.0.1:<port>."""
    port = settings.tile_server_port
    log.info("serving %s on http://127.0.0.1:%d (Ctrl+C to stop)", settings.tiles_dir, port)
    external.run(["pmtiles", "serve", settings.tiles_dir, "--port", str(port), "--cors", "*"])
