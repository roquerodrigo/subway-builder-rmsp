"""Acquire raw data: download the Geofabrik PBF and the Pesquisa OD zip, clip the
PBF to the city bbox, and extract per-layer GeoJSONSeq subsets with osmium."""

from __future__ import annotations

import logging
import urllib.request
import zipfile
from pathlib import Path

from rmsp import external
from rmsp.config import settings

log = logging.getLogger(__name__)

# layer name -> (osmium tags-filter expressions, export geometry types, extra export args)
LAYERS: dict[str, tuple[list[str], str, list[str]]] = {
    "roads": (
        [
            "w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,"
            "secondary,secondary_link,tertiary,tertiary_link,residential,living_street,"
            "unclassified,road"
        ],
        "linestring",
        ["-a", "type"],
    ),
    "buildings": (["a/building"], "polygon", []),
    "water": (["a/natural=water", "a/landuse=reservoir", "a/water"], "polygon", []),
    "aero": (["nwr/aeroway=runway,taxiway,apron,aerodrome"], "polygon,linestring", []),
    "parks": (
        [
            "a/leisure=park,nature_reserve,garden",
            "a/landuse=forest,grass,recreation_ground,meadow,village_green",
            "a/natural=wood",
        ],
        "polygon",
        [],
    ),
}


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        log.info("already downloaded: %s", dest.name)
        return
    log.info("downloading %s -> %s", url, dest.name)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:  # noqa: S310
        while chunk := r.read(1 << 20):
            f.write(chunk)


def download() -> None:
    settings.ensure_dirs()
    _download(settings.geofabrik_pbf_url, settings.pbf)
    od_url = settings.od2023_zip_url if settings.od_year == 2023 else settings.od2017_zip_url
    od_zip = settings.sources_dir / f"od{settings.od_year}.zip"
    _download(od_url, od_zip)
    od_dir = settings.sources_dir / f"od{settings.od_year}"
    if not od_dir.exists():
        log.info("extracting %s", od_zip.name)
        with zipfile.ZipFile(od_zip) as z:
            z.extractall(od_dir)


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


def extract() -> None:
    """Extract each layer subset from the clipped PBF into <layer>.geojsonseq."""
    src = settings.sources_dir
    for name, (filters, gtypes, extra) in LAYERS.items():
        tmp_pbf = src / f"_{name}.pbf"
        out = src / f"{name}.geojsonseq"
        log.info("extracting %s", name)
        external.run(
            ["osmium", "tags-filter", "-o", tmp_pbf, "--overwrite", settings.pbf_clip, *filters]
        )
        external.run(
            [
                "osmium",
                "export",
                tmp_pbf,
                "-o",
                out,
                "-f",
                "geojsonseq",
                f"--geometry-types={gtypes}",
                *extra,
                "--overwrite",
            ]
        )
        tmp_pbf.unlink(missing_ok=True)


def acquire() -> None:
    """Full source step: download + clip + extract."""
    download()
    clip()
    extract()
