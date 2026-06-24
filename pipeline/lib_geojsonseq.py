"""Helpers shared by the OSM formatters."""
import json


def read_features(path):
    """Yield Feature dicts from an osmium GeoJSONSeq file (RS-delimited)."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def outer_rings(geom):
    """Return list of outer rings ([[lng,lat],...]) for Polygon/MultiPolygon."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"][0]] if geom["coordinates"] else []
    if t == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"] if poly]
    return []
