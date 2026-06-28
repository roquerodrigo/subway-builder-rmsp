"""Package the city into the Railyard map-distribution format.

A published map is a single ZIP (flat, no subfolders) holding ``config.json`` +
the game data files + ``<CODE>.pmtiles``, plus an "Update JSON" the game reads to
install/update the map. The registry's integrity check accepts the data files
gzipped, so we reuse the ``.gz`` the pipeline already produces. Foundations are
derived from ``buildings_index`` at runtime, so the single basemap PMTiles is enough
(no foundations tiles in a published map).

Refs: subwaybuildermodded.com/railyard/docs/v0.2/developers/publishing-projects and
the registry integrity validation (scripts/lib/integrity.ts).
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from datetime import date

from rmsp.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)


def _sync_mod_version(version: str) -> None:
    """Keep mod/manifest.json's version in lockstep with the released map version.

    Always called by :func:`bundle`, so the in-game mod version and the published map
    version never drift — no need to remember to bump the manifest by hand on a release.
    """
    path = PROJECT_ROOT / "mod" / "manifest.json"
    m = json.loads(path.read_text("utf-8"))
    if m.get("version") != version:
        m["version"] = version
        path.write_text(json.dumps(m, ensure_ascii=False, indent=4) + "\n", "utf-8")
        log.info("synced mod/manifest.json version -> %s", version)

# Game data files, in the gzipped form the registry accepts. ocean_depth_index is
# optional (not in the required set) but RMSP has reservoirs, so ship it when present.
_DATA_FILES = (
    "demand_data.json.gz",
    "buildings_index.json.gz",
    "roads.geojson.gz",
    "runways_taxiways.geojson.gz",
)
_OPTIONAL_DATA_FILES = ("ocean_depth_index.json.gz",)


def _config(version: str) -> dict:
    """config.json — the registry requires code, version and a numeric
    initialViewState; the game also reads name/population/minZoom for the city."""
    return {
        "code": settings.code,
        "name": settings.name,
        "description": settings.description,
        "version": version,
        "country": "BR",
        "population": settings.population,
        "minZoom": settings.min_zoom,
        "initialViewState": {
            "latitude": settings.center_lat,
            "longitude": settings.center_lng,
            "zoom": settings.zoom,
            "bearing": 0,
        },
    }


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle(
    version: str = "1.0.0",
    repo: str | None = None,
    changelog: str = "Primeira versão.",
) -> None:
    """Write data/dist/<CODE>.zip (the release asset) and data/dist/<CODE>.json
    (the Update JSON). ``repo`` is the GitHub repo URL used to build the download
    link, e.g. https://github.com/<owner>/subway-builder-rmsp."""
    dist = settings.data_dir / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    _sync_mod_version(version)  # mod manifest tracks the release version automatically

    pmtiles = settings.tiles_dir / f"{settings.code}.pmtiles"
    if not pmtiles.exists():
        raise RuntimeError(f"missing {pmtiles} — run `rmsp tiles` first")

    cfg = dist / "config.json"
    cfg.write_text(json.dumps(_config(version), ensure_ascii=False, indent=2), "utf-8")

    # gather flat members (config + data .gz + the basemap pmtiles)
    members = [cfg, pmtiles]
    for name in _DATA_FILES:
        src = settings.build_dir / name
        if not src.exists():
            raise RuntimeError(f"missing {src} — run `rmsp build` first")
        members.append(src)
    for name in _OPTIONAL_DATA_FILES:
        src = settings.build_dir / name
        if src.exists():
            members.append(src)
        else:
            log.warning("optional %s not built — skipping", name)

    zip_path = dist / f"{settings.code}.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for m in members:
            # config.json compresses; .gz/.pmtiles are already compressed -> store
            compress = zipfile.ZIP_DEFLATED if m.suffix == ".json" else zipfile.ZIP_STORED
            z.write(m, arcname=m.name, compress_type=compress)

    sha = _sha256(zip_path)
    log.info(
        "bundle -> %s (%.1f MB)  sha256=%s",
        zip_path.relative_to(settings.data_dir),
        zip_path.stat().st_size / 1e6,
        sha,
    )
    log.info("  files: %s", ", ".join(m.name for m in members))

    download = (
        f"{repo.rstrip('/')}/releases/download/v{version}/{settings.code}.zip"
        if repo
        else f"<RELEASE_URL>/{settings.code}.zip"
    )
    update = {
        "schema_version": 1,
        "versions": [
            {
                "version": version,
                "game_version": ">=1.0.0",
                "date": date.today().isoformat(),
                "changelog": changelog,
                "download": download,
                "sha256": sha,
            }
        ],
    }
    upd = dist / f"{settings.code}.json"
    upd.write_text(json.dumps(update, ensure_ascii=False, indent=2), "utf-8")
    log.info("update json -> %s", upd.relative_to(settings.data_dir))
    if not repo:
        log.warning("no --repo given: fill in the `download` URL in %s", upd.name)
