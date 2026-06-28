"""Acquire raw data: download the Geofabrik PBF and the Pesquisa OD zip, clip the
PBF to the city bbox, and extract per-layer GeoJSONSeq subsets with osmium."""

from __future__ import annotations

import logging
import re
import ssl
import urllib.request
import zipfile
from pathlib import Path

from rmsp import external, geojson
from rmsp.config import settings

log = logging.getLogger(__name__)


def _ssl_context() -> ssl.SSLContext | None:
    """Verifying context backed by certifi's CA bundle. The IBGE FTP-over-HTTPS host
    serves an incomplete chain that Python's default store rejects (certifi has the
    root), so prefer it; fall back to the default store if certifi is unavailable."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None

# layer name -> (osmium tags-filter expressions, export geometry types, extra export args)
LAYERS: dict[str, tuple[list[str], str, list[str]]] = {
    "roads": (
        [
            "w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,"
            "secondary,secondary_link,tertiary,tertiary_link,residential,living_street,"
            "unclassified,road,"
            # pedestrian path types — build_roads keeps only the ones inside a park
            # (so the city isn't flooded with sidewalks/crossings), to draw park trails
            "footway,path,pedestrian,cycleway,steps"
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
    with urllib.request.urlopen(req, context=_ssl_context()) as r, open(dest, "wb") as f:  # noqa: S310
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


def cnefe() -> None:
    """Build the compact CNEFE address-point file for the dasymetric demand proxy.

    Downloads the IBGE Censo 2022 CNEFE zip for São Paulo state (~1 GB), streams the CSV
    inside it (never extracting the multi-GB file to disk), and writes ``cnefe.csv`` —
    only ``lng,lat,especie`` for addresses inside the city bbox whose espécie is kept.
    No-op unless ``demand_proxy == "cnefe"``."""
    if settings.demand_proxy != "cnefe":
        return
    out = settings.cnefe_csv
    if out.exists():
        log.info("already built: %s", out.name)
        return
    _download(settings.cnefe_url, settings.cnefe_zip)
    skip = settings.cnefe_skip_especies
    levels = settings.cnefe_coord_levels
    log.info("filtering CNEFE -> %s (bbox %s)", out.name, settings.bbox)
    n = kept = 0
    with zipfile.ZipFile(settings.cnefe_zip) as z:
        name = next(m for m in z.namelist() if m.lower().endswith(".csv"))
        with z.open(name) as raw, open(out, "w", encoding="ascii") as fout:
            header = raw.readline().decode("latin-1").rstrip("\r\n").split(";")
            col = {c: i for i, c in enumerate(header)}
            ilng, ilat = col["LONGITUDE"], col["LATITUDE"]
            iesp, inv, isetor = col["COD_ESPECIE"], col["NV_GEO_COORD"], col["COD_SETOR"]
            for line in raw:
                n += 1
                f = line.decode("latin-1").rstrip("\r\n").split(";")
                try:
                    especie = int(f[iesp])
                    if especie in skip:
                        continue
                    if levels is not None and int(f[inv]) not in levels:
                        continue
                    lng, lat = float(f[ilng]), float(f[ilat])
                except (ValueError, IndexError):
                    continue
                if not settings.in_bbox(lng, lat):
                    continue
                setor = re.sub(r"\D+$", "", f[isetor])  # drop the 1-char situation suffix
                fout.write(f"{lng},{lat},{especie},{setor}\n")
                kept += 1
    log.info("CNEFE: scanned=%d kept=%d -> %s (%.1f MB)", n, kept, out.name, geojson.mb(out))


def censo() -> None:
    """Build setor_pop.csv (``setor,pop``) from the IBGE Censo 2022 setor aggregates.

    Downloads the ~15 MB Brazil "Básico" table and keeps the resident population (v0001)
    of every São Paulo (UF 35) census tract, for the CNEFE residential weighting. No-op
    unless the CNEFE proxy with census weighting is active."""
    if settings.demand_proxy != "cnefe" or not settings.censo_use_pop_weight:
        return
    out = settings.setor_pop_csv
    if out.exists():
        log.info("already built: %s", out.name)
        return
    _download(settings.censo_basico_url, settings.censo_basico_zip)
    log.info("parsing Censo setor population -> %s", out.name)

    def cells(line: bytes) -> list[str]:
        return [c.strip().strip('"') for c in line.decode("latin-1").rstrip("\r\n").split(";")]

    n = kept = 0
    with zipfile.ZipFile(settings.censo_basico_zip) as z:
        name = next(m for m in z.namelist() if m.lower().endswith(".csv"))
        with z.open(name) as raw, open(out, "w", encoding="ascii") as fout:
            header = cells(raw.readline())
            isetor, ipop = header.index("CD_SETOR"), header.index("v0001")
            for line in raw:
                n += 1
                f = cells(line)
                try:
                    setor = f[isetor]
                    pop = int(f[ipop] or 0)
                except (ValueError, IndexError):
                    continue
                if pop <= 0 or not setor.startswith("35"):  # UF 35 = São Paulo
                    continue
                fout.write(f"{setor},{pop}\n")
                kept += 1
    log.info("Censo: scanned=%d kept(SP setores)=%d -> %s", n, kept, out.name)


def acquire() -> None:
    """Full source step: download + clip + extract (+ CNEFE/Censo when that proxy is selected)."""
    download()
    clip()
    extract()
    cnefe()
    censo()
