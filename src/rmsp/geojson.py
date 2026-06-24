"""Helpers for reading osmium GeoJSONSeq output and writing the game's gzip files."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

RS = "\x1e"  # record separator that osmium prefixes each GeoJSONSeq line with


def read_features(path: Path) -> Iterator[dict[str, Any]]:
    """Yield Feature dicts from an osmium GeoJSONSeq file (RS-delimited)."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.lstrip(RS).strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def outer_rings(geom: dict[str, Any]) -> list[list[list[float]]]:
    """Outer rings ([[lng,lat],...]) for a Polygon/MultiPolygon geometry."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"][0]] if geom["coordinates"] else []
    if t == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"] if poly]
    return []


def write_json(obj: Any, path: Path) -> None:
    """Write compact JSON (uncompressed)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def write_json_gz(obj: Any, path: Path) -> None:
    """Write compact gzipped JSON (the format the game loads)."""
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def mb(path: Path) -> float:
    return path.stat().st_size / 1e6
