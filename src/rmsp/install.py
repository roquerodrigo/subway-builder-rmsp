"""Install the mod (index.js + manifest.json) and the generated data files into
the game (resolved from SB_DATA_DIR)."""

from __future__ import annotations

import logging
import shutil

from rmsp.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)

DATA_FILES = [
    "roads.geojson.gz",
    "buildings_index.json.gz",
    "ocean_depth_index.json.gz",
    "runways_taxiways.geojson.gz",
    "demand_data.json.gz",
]


def install() -> None:
    mod_src = PROJECT_ROOT / "mod"
    settings.mod_dir.mkdir(parents=True, exist_ok=True)
    for f in ("index.js", "manifest.json"):
        shutil.copy2(mod_src / f, settings.mod_dir / f)
    log.info("installed mod -> %s", settings.mod_dir)

    # The game resolves city data from the mod's data/ AND the by-code cities dir;
    # write both so it's found either way.
    for dest in (settings.mod_data, settings.city_data):
        dest.mkdir(parents=True, exist_ok=True)
        for name in DATA_FILES:
            src = settings.build_dir / name
            if src.exists():
                shutil.copy2(src, dest / name)
        log.info("installed data -> %s", dest)

    log.info("enable the mod (br.rodrigo.rmsp) in Settings > Mods and restart the game")
