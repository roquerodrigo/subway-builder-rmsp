"""Reapply RMSP's performance patch to the installed ``depot`` library.

depot's ``MapGen._process_tile_worker`` (the "Fixing MBTiles" step) stalls for ~1 h on
RMSP's dense water geometry. This patch removes the two pathological hot spots:

1. an ``O(parts × water_features)`` id-association loop — quadratic on the Billings/
   Guarapiranga/Tietê tiles;
2. the shapely ``difference`` of every park and commercial polygon against the huge
   dissolved reservoir geometry (depot 1.2.3 added the commercial layer to this).

Trade-off: parks and commercial areas may slightly overlap water at some zooms. The
park×aerodrome and park×commercial differences depot 1.2.3 introduced are kept — those
masks are small, so they cost little and improve the rendered result. Everything else
(the ``class``→``kind`` rename the game needs, tile clipping, the dissolve) is untouched.

Each patch is anchored on a single source line rather than a whole block, so nearby
edits upstream do not silently break the match.

The patch lives in the venv (``site-packages/depot/maps.py``) and is **lost on
``uv sync`` or any depot reinstall**. It is re-applied automatically by
:func:`rmsp.generate.generate_base` before the tile step (in time for depot's spawned
tile workers, which re-import ``depot.maps`` from disk). To apply it by hand:

    uv run python -m rmsp.depot_patch

Idempotent; a no-op once the ``PATCH (rmsp)`` marker is present.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_MARKER = "PATCH (rmsp)"

# (label, anchor line, replacement, expected occurrences). Anchors are matched without
# their leading indentation, so the replacement inherits the original indentation.
_PATCHES: list[tuple[str, str, str, int]] = [
    (
        "quadratic water id-association loop",
        "for orig_id, orig_geom in water_id_map:",
        "for orig_id, orig_geom in ():  # PATCH (rmsp): drop the "
        "O(parts x water_features) loop; the water feature id is non-essential metadata",
        1,
    ),
    (
        "park/commercial x water difference",
        "if merged_result is not None and not merged_result.is_empty:",
        "if False:  # PATCH (rmsp): skip the difference against the dissolved reservoir "
        "geometry, which stalls the fix step for ~1 h on RMSP",
        2,
    ),
]


def ensure_patched(verbose: bool = True) -> bool:
    """Apply the patch to depot's ``maps.py`` if not already applied.

    Returns True if the file was changed. Safe to call repeatedly; logs a warning and
    leaves that anchor untouched if depot's source has drifted.
    """
    import depot.maps as m

    path = Path(m.__file__)
    src = path.read_text(encoding="utf-8")
    if _MARKER in src:
        return False
    applied = 0
    for label, old, new, occurrences in _PATCHES:
        found = src.count(old)
        if found != occurrences:
            log.warning(
                "depot patch: anchor %r found %d time(s), expected %d — depot source changed?",
                label,
                found,
                occurrences,
            )
            continue
        src = src.replace(old, new)
        applied += 1
    if applied:
        path.write_text(src, encoding="utf-8")
        if verbose:
            log.info("depot patch: applied %d/%d anchor(s) to %s", applied, len(_PATCHES), path)
    return applied > 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    changed = ensure_patched()
    print("depot patched" if changed else "depot already patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
