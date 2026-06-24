"""Vector basemap: build PMTiles from the OSM subsets (tippecanoe) and serve them.

Layer names match the game's style so it renders water/parks/buildings/airports:
  - RMSP.pmtiles            -> water, parks, airports, buildings
  - RMSP_foundations.pmtiles -> foundations (buildings), ocean_foundations (water)
"""

from __future__ import annotations

import logging
from pathlib import Path

from rmsp import external
from rmsp.config import settings

log = logging.getLogger(__name__)

# tippecanoe layer name -> source geojsonseq stem (RS-stripped to ndjson first)
_NDJSON = ["water", "buildings", "aero", "parks"]


def _to_ndjson() -> None:
    """Strip the RS (0x1e) byte osmium prefixes so tippecanoe reads plain NDJSON."""
    for stem in _NDJSON:
        src = settings.sources_dir / f"{stem}.geojsonseq"
        dst = settings.sources_dir / f"{stem}.ndjson"
        dst.write_bytes(src.read_bytes().replace(b"\x1e", b""))


def _nd(stem: str) -> Path:
    return settings.sources_dir / f"{stem}.ndjson"


def build_tiles() -> None:
    settings.ensure_dirs()
    _to_ndjson()
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
            "--drop-densest-as-needed",
            "--coalesce-densest-as-needed",
            "--extend-zooms-if-still-dropping",
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
