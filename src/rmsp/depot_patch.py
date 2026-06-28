"""Reapply RMSP's performance patch to the installed ``depot`` library.

depot's ``MapGen._process_tile_worker`` (the "Fixing MBTiles" step) stalls for ~1 h on
RMSP's dense water geometry. This patch removes the two pathological hot spots:

1. an ``O(parts × water_features)`` id-association loop — quadratic on the Billings/
   Guarapiranga/Tietê tiles;
2. the park×water / park×aerodrome shapely ``difference`` against the huge dissolved
   reservoir geometry.

Trade-off: parks may slightly overlap water at some zooms. Everything else (the
``class``→``kind`` rename the game needs, tile clipping, the dissolve) is untouched.

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
_I = " " * 16  # the worker body is indented 16 spaces

# (label, original block, replacement block). Whitespace must match depot's source
# byte-for-byte — note the 16-space blank line in block 1 and the empty lines in block 2.
_PATCHES: list[tuple[str, str, str]] = [
    (
        "quadratic water id-association loop",
        "\n".join(
            [
                _I + "associated_ids = []",
                _I + "for orig_id, orig_geom in water_id_map:",
                _I + "    if part.intersects(orig_geom):",
                _I + "        associated_ids.append(orig_id)",
                _I + "",
                _I + "# Determine the primary ID (using the first one found)",
                _I + "primary_id = associated_ids[0] if associated_ids else None",
            ]
        ),
        "\n".join(
            [
                _I + "# PATCH (rmsp): skip the O(parts × water_features) id-association loop —",
                _I + "# quadratic and pathologically slow on dense-water tiles (Billings/",
                _I + "# Guarapiranga/Tietê); the water feature id is non-essential metadata.",
                _I + "primary_id = None",
            ]
        ),
    ),
    (
        "park×water difference",
        "\n".join(
            [
                _I + "# Subtract water from parks and aerodromes",
                _I + "if merged_result is not None and not merged_result.is_empty:",
                _I + "    if geom.intersects(merged_result):",
                _I + "        geom = geom.difference(merged_result)",
                _I + "        if not geom.is_valid:",
                _I + "            geom = geom.buffer(0)",
                "",
                _I + "# Subtract aerodromes from parks",
                _I + 'if kind == "park" and aerodrome_mask is not None and not aerodrome_mask.is_empty:',  # noqa: E501
                _I + "    if geom.intersects(aerodrome_mask):",
                _I + "        geom = geom.difference(aerodrome_mask)",
                _I + "        if not geom.is_valid:",
                _I + "            geom = geom.buffer(0)",
                "",
                _I + "# Final geometry verification & cleaning",
            ]
        ),
        "\n".join(
            [
                _I + "# PATCH (rmsp): skip park×water and park×aerodrome difference — the shapely",
                _I + "# difference against the huge dissolved reservoir geometry is what stalls the",  # noqa: E501
                _I + "# fix step for ~1h on RMSP. Parks may slightly overlap water at some zooms",
                _I + "# (accepted trade-off); everything else (kind rename, clipping to tile) stays.",  # noqa: E501
                "",
                _I + "# Final geometry verification & cleaning",
            ]
        ),
    ),
]


def ensure_patched(verbose: bool = True) -> bool:
    """Apply the patch to depot's ``maps.py`` if not already applied.

    Returns True if the file was changed. Safe to call repeatedly; logs a warning and
    leaves the file untouched if depot's source has drifted (a block no longer matches).
    """
    import depot.maps as m

    path = Path(m.__file__)
    src = path.read_text(encoding="utf-8")
    if _MARKER in src:
        return False
    applied = 0
    for label, old, new in _PATCHES:
        if old not in src:
            log.warning("depot patch: block %r not found — depot source changed?", label)
            continue
        src = src.replace(old, new, 1)
        applied += 1
    if applied:
        path.write_text(src, encoding="utf-8")
        if verbose:
            log.info("depot patch: applied %d/%d block(s) to %s", applied, len(_PATCHES), path)
    return applied > 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    changed = ensure_patched()
    print("depot patched" if changed else "depot already patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
