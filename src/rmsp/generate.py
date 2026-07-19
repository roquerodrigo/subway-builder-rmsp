"""Generate the non-demand game files via `depot` (the official SBM map-making library).

`depot.maps.MapGen` produces roads, the buildings index (both ``buildings_index.json``
and the newer ``buildings_index.bin``), airports, the ocean-depth index and the PMTiles
basemap from an OSM PBF + Overture buildings. This module builds a MapGen from
:data:`~rmsp.config.settings`, runs the base+tiles steps, then **collects** the outputs
(gzipping the plain ones) into ``data/build/`` and ``data/tiles/`` so the demand pipeline,
``validate`` and ``publish`` (the Railyard map bundle) find them where they already look.

Demand is downloaded from the demand-data release (:mod:`rmsp.demand`) and routed by
:mod:`rmsp.routing` — depot does not do demand.

depot requires several CLI tools on PATH (node, mapshaper, osmium, java, tippecanoe,
tile-join, sqlite3, jq, pmtiles, planetiler.jar); its constructor raises if any is missing.
"""

from __future__ import annotations

import gzip
import json
import logging
import shutil
from pathlib import Path

from rmsp.config import settings

log = logging.getLogger(__name__)


def _mapgen(verbose: bool):
    """Construct a depot MapGen from settings. depot writes to ``<outputdir>/<CODE>/``."""
    from depot.maps import MapGen

    settings.ensure_dirs()  # data/ (outputdir) + build/ + tiles/ + sources/
    if not settings.pbf.exists():
        raise RuntimeError(f"missing {settings.pbf} — run `rmsp sources` first")
    return MapGen(
        city=settings.code,
        bbox=list(settings.bbox),
        osmpbf=str(settings.pbf),
        outputdir=str(settings.data_dir),
        maxzoom=settings.maxzoom,
        ncores=settings.n_build_workers(),
        building_index_filter_size=settings.bldg_area_min_m2,
        building_index_simplification=settings.building_index_simplification,
        max_building_tile_size=settings.max_building_tile_kb or None,  # 0 -> None (no cap)
        create_building_foundations=settings.create_building_foundations,
        create_ocean_foundations=settings.create_ocean_foundations,
        cities=settings.label_cities,
        suburbs=settings.label_suburbs,
        neighborhoods=settings.label_neighborhoods,
        RAM=settings.mapshaper_ram_gb,
        verb=verbose,
    )


def _prefilter_buildings(src: Path) -> Path:
    """Drop sub-``bldg_prefilter_m2`` structures from depot's Overture ``buildings.geojson``
    before mapshaper. Overture emits ~7M tiny features for the whole metro and mapshaper's
    ``-clean`` OOMs loading them all; cutting below a guard threshold (under the map's final
    ``bldg_area_min_m2``) leaves mapshaper's own filter to make the identical final cut on a
    fraction of the input. Streams line-by-line (one Feature per line) so memory stays flat.

    Area is the exterior-ring shoelace in deg² scaled by the local m/deg factors — a fast
    equirectangular approximation, well within tolerance for a size cull.
    """
    mlat, mlng = settings.m_per_deg_lat, settings.m_per_deg_lng
    thresh = settings.bldg_prefilter_m2
    dst = src.with_name("buildings_prefiltered.geojson")
    kept = total = 0
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
        fout.write('{"type":"FeatureCollection","name":"buildings","features":[\n')
        first = True
        for line in fin:
            s = line.strip().rstrip(",")
            if not (s.startswith("{") and '"Feature"' in s[:40]):
                continue  # header / bracket lines
            total += 1
            try:
                geom = json.loads(s)["geometry"]
                coords = geom["coordinates"]
                # exterior ring: Polygon -> coords[0]; MultiPolygon -> first polygon's coords[0][0]
                ring = coords[0][0] if geom["type"] == "MultiPolygon" else coords[0]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
            a = 0.0
            for i in range(len(ring) - 1):
                a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
            if abs(a) * 0.5 * mlat * mlng < thresh:
                continue
            fout.write(s if first else ",\n" + s)
            first = False
            kept += 1
        fout.write("\n]}\n")
    log.info(
        "pre-filtered buildings: kept %d / %d (>= %.0f m²) -> %s", kept, total, thresh, dst.name
    )
    return dst


def _gzip_to(src: Path, dst: Path) -> None:
    with open(src, "rb") as f_in, gzip.open(dst, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)


def _collect_gzipped(city_dir: Path, build_dir: Path, name: str) -> None:
    """Take depot's own ``<name>.gz`` when it wrote one, else gzip the plain file.

    depot 1.2.4 gzips the buildings index itself; roads and runways still come out plain.
    """
    already_gzipped = city_dir / f"{name}.gz"
    if already_gzipped.exists():
        shutil.copy2(already_gzipped, build_dir / already_gzipped.name)
    else:
        _gzip_to(city_dir / name, build_dir / f"{name}.gz")


def _collect() -> None:
    """Move depot's ``data/<CODE>/`` outputs into build_dir/tiles_dir (gzipping plain ones)."""
    city_dir = settings.data_dir / settings.code
    build_dir = settings.build_dir
    for name in ("buildings_index.json", "roads.geojson", "runways_taxiways.geojson"):
        _collect_gzipped(city_dir, build_dir, name)
    # depot only ever writes these gzipped.
    for name in ("buildings_index.bin.gz", "ocean_depth_index.json.gz"):
        src = city_dir / name
        if src.exists():
            shutil.copy2(src, build_dir / name)
        else:
            log.warning("depot did not produce %s — skipping", name)
    pmtiles = f"{settings.code}.pmtiles"
    shutil.copy2(city_dir / pmtiles, settings.tiles_dir / pmtiles)


def generate_base(verbose: bool = False) -> None:
    """Run depot end-to-end for the non-demand files, then collect the outputs.

    Equivalent to ``MapGen.run_all()`` (extract -> buildings -> roads/aeroways -> pmtiles
    -> labels) followed by the collect step. Produces in ``data/build/``:
    ``buildings_index.json.gz`` + ``buildings_index.bin.gz``, ``roads.geojson.gz``,
    ``runways_taxiways.geojson.gz``, ``ocean_depth_index.json.gz``; and
    ``data/tiles/<CODE>.pmtiles``.
    """
    g = _mapgen(verbose)
    g.extract_base_data()
    # Pre-filter the Overture buildings before process_buildings' mapshaper step (which OOMs
    # on the whole-metro ~7M features). Reuse depot's cached buildings.geojson if present,
    # else let depot fetch it; then point depot at the reduced file.
    raw = settings.data_dir / settings.code / "buildings.geojson"
    if not raw.exists():
        g._fetch_overture_buildings()  # depot writes buildings.geojson + sets g.buildings_geojson
        raw = Path(g.buildings_geojson)
    g.buildings_geojson = str(_prefilter_buildings(raw))
    g.process_buildings()
    g.process_roads_and_aeroways()
    g.generate_pmtiles()
    g.add_labels()
    _collect()
    log.info("generated base files -> %s + %s", settings.build_dir, settings.tiles_dir)
