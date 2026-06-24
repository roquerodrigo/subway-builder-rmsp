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
    # green/recreation areas: parks, gardens, reserves, forests, protected areas
    "parks": (
        [
            "a/leisure=park,nature_reserve,garden,recreation_ground,dog_park",
            "a/landuse=forest,grass,recreation_ground,meadow,village_green,greenfield",
            "a/natural=wood,scrub,grassland,heath",
            "a/boundary=national_park,protected_area",
        ],
        "polygon",
        [],
    ),
    # place labels (points): the game renders city_labels / suburb_labels /
    # neighborhood_labels symbol layers from `name`. tiles.py splits these by class.
    "places": (
        ["n/place=city,town,suburb,borough,neighbourhood,quarter,hamlet,village"],
        "point",
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
    _download(settings.od_zip_url, settings.od_zip)
    if not settings.od_dir.exists():
        log.info("extracting %s", settings.od_zip.name)
        with zipfile.ZipFile(settings.od_zip) as z:
            z.extractall(settings.od_dir)


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
