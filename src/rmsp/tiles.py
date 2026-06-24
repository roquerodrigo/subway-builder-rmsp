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

# layers that go straight to NDJSON (just strip osmium's RS byte)
_PLAIN_NDJSON = ["water", "buildings", "aero"]


def _to_ndjson() -> None:
    """Strip the RS (0x1e) byte osmium prefixes so tippecanoe reads plain NDJSON."""
    for stem in _PLAIN_NDJSON:
        src = settings.sources_dir / f"{stem}.geojsonseq"
        dst = settings.sources_dir / f"{stem}.ndjson"
        dst.write_bytes(src.read_bytes().replace(b"\x1e", b""))


def _parks_ndjson() -> None:
    """Write parks.ndjson with an `area` (m²) property. The game's parks-large /
    parks-small layers filter on `["get","area"]` (>= / < 1e5), so without it
    no green area renders (this is what London's tiles carry)."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    to_m = Transformer.from_crs("EPSG:4326", settings.metric_crs, always_xy=True).transform
    dst = settings.sources_dir / "parks.ndjson"
    n = 0
    with open(dst, "w", encoding="utf-8") as out:
        for ft in geojson.read_features(settings.sources_dir / "parks.geojsonseq"):
            geom = ft.get("geometry")
            if not geom:
                continue
            try:
                area = transform(to_m, shape(geom)).area
            except Exception:
                continue
            props = ft.get("properties") or {}
            props["area"] = round(area)
            ft["properties"] = props
            out.write(json.dumps(ft, separators=(",", ":")) + "\n")
            n += 1
    log.info("parks with area: %d -> %s", n, dst.name)


def _nd(stem: str) -> Path:
    return settings.sources_dir / f"{stem}.ndjson"


def build_tiles() -> None:
    settings.ensure_dirs()
    _to_ndjson()
    _parks_ndjson()
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
