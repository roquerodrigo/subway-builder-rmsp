"""Helpers for reading osmium GeoJSONSeq output and writing the game's gzip files."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

RS = "\x1e"  # record separator that osmium prefixes each GeoJSONSeq line with
_RS_B = b"\x1e"


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


def chunk_offsets(path: Path, n: int) -> list[tuple[int, int]]:
    """Split a file into ``n`` contiguous [start, end) byte ranges for parallel reads.

    Ranges cut at arbitrary byte offsets; :func:`read_features_range` realigns to whole
    lines so every record is read by exactly one range (no splits, no gaps)."""
    size = path.stat().st_size
    if n <= 1 or size == 0:
        return [(0, size)]
    step = size // n
    bounds = [i * step for i in range(n)] + [size]
    return [(s, e) for s, e in zip(bounds[:-1], bounds[1:], strict=True) if s < e]


def read_lines_range(path: Path, start: int, end: int) -> Iterator[bytes]:
    """Yield non-empty, stripped raw lines whose start falls within [start, end).

    A line straddling ``start`` belongs to the previous range (skipped here); a line
    straddling ``end`` started before it, so this range reads it whole. Pairs with
    :func:`chunk_offsets` to partition any line-delimited file across worker processes
    losslessly. Generic over content — callers decode/parse the bytes themselves."""
    with open(path, "rb") as f:
        if start:
            f.seek(start)
            f.readline()  # partial line belongs to the previous range
        while f.tell() < end:
            raw = f.readline()
            if not raw:
                break
            raw = raw.strip()
            if raw:
                yield raw


def read_features_range(path: Path, start: int, end: int) -> Iterator[dict[str, Any]]:
    """Yield Features whose line begins within [start, end) of a GeoJSONSeq file."""
    for raw in read_lines_range(path, start, end):
        try:
            yield json.loads(raw.lstrip(_RS_B))
        except json.JSONDecodeError:
            continue


def parallel_chunks(path: Path, worker: Any, workers: int, *args: Any) -> list[Any]:
    """Run ``worker(path, start, end, *args)`` over byte-range chunks of ``path``.

    ``worker`` must be a module-level (picklable) function. Results are returned in
    file order (chunk 0 first), so concatenating list-valued partials reproduces a
    sequential single-pass scan exactly. Falls back to an in-process call when the
    file yields a single chunk, avoiding pool/spawn overhead for tiny inputs."""
    from concurrent.futures import ProcessPoolExecutor

    ranges = chunk_offsets(path, max(1, workers))
    if len(ranges) <= 1:
        s, e = ranges[0]
        return [worker(path, s, e, *args)]
    with ProcessPoolExecutor(max_workers=len(ranges)) as ex:
        futs = [ex.submit(worker, path, s, e, *args) for s, e in ranges]
        return [f.result() for f in futs]


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


# gzip level 6 ≈ level 9's size on this JSON (within ~0.1%) but ~6× faster to write;
# the game only gunzips, so the level is irrelevant to it. Level 9 was costing ~44 s
# on the 68 MB buildings index alone.
GZIP_LEVEL = 6


def write_json_gz(obj: Any, path: Path, compresslevel: int = GZIP_LEVEL) -> None:
    """Write compact gzipped JSON (the format the game loads)."""
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=compresslevel) as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def mb(path: Path) -> float:
    return path.stat().st_size / 1e6
