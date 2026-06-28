"""Acquire the base map source: download the Geofabrik PBF and clip it to the city bbox.

Demand is no longer built here — it is downloaded from the demand-data release
(:mod:`rmsp.demand`). The PBF feeds depot's tile/building/road generation and the OSRM
routing graph.
"""

from __future__ import annotations

import logging
import ssl
import urllib.request
from pathlib import Path

from rmsp import external
from rmsp.config import settings

log = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext | None:
    """Verifying context backed by certifi's CA bundle when available."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        log.info("already downloaded: %s", dest.name)
        return
    log.info("downloading %s -> %s", url, dest.name)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=_ssl_context()) as r, open(dest, "wb") as f:  # noqa: S310
        while chunk := r.read(1 << 20):
            f.write(chunk)


def download() -> None:
    """Download the Geofabrik sudeste PBF (basemap generation + routing source)."""
    settings.ensure_dirs()
    _download(settings.geofabrik_pbf_url, settings.pbf)


def clip() -> None:
    """Clip the sudeste PBF to the city bbox (osmium extract, smart strategy)."""
    if settings.pbf_clip.exists():
        log.info("already clipped: %s", settings.pbf_clip.name)
        return
    b = settings.bbox
    log.info("clipping PBF to bbox %s", b)
    external.run(
        [
            "osmium",
            "extract",
            "-b",
            f"{b[0]},{b[1]},{b[2]},{b[3]}",
            settings.pbf,
            "-o",
            settings.pbf_clip,
            "-s",
            "smart",
            "--overwrite",
        ]
    )


def acquire() -> None:
    """Full source step: download the PBF and clip it to the bbox."""
    download()
    clip()
