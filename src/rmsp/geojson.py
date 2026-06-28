"""Helpers for writing/reading the game's compact gzip JSON files."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def write_json(obj: Any, path: Path) -> None:
    """Write compact JSON (uncompressed)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


# level 6 ≈ level 9's size on this JSON (within ~0.1%) but ~6× faster to write; the game
# only gunzips, so the level is irrelevant to it (level 9 cost ~44 s on the buildings index).
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
