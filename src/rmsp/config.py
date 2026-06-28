"""Single source of truth for the RMSP build: city params, tuning knobs, paths.

Every scalar knob (str/int/float/bool) can be overridden from the environment or a
``.env`` file at the project root — the env var name is shown next to each field. A real
shell ``export`` wins over ``.env`` (``load_dotenv`` does not clobber vars already set).
Copy ``.env.example`` to ``.env`` to change the build without touching code. Non-scalar
knobs (dicts/tuples/sets) stay as code constants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

_FALSEY = {"0", "false", "no", ""}


def _env(name: str, default, cast):
    """A dataclass field defaulting to ``cast(os.environ[name])``, else *default*.

    Casting is deferred to instantiation via ``default_factory`` so ``.env`` (loaded
    above) is already in ``os.environ`` by the time it runs.
    """

    def factory(n=name, d=default, c=cast):
        raw = os.environ.get(n)
        return d if raw is None or raw == "" else c(raw)

    return field(default_factory=factory)


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() not in _FALSEY


def env_str(name: str, default: str):
    return _env(name, default, str)


def env_int(name: str, default: int):
    return _env(name, default, int)


def env_float(name: str, default: float):
    return _env(name, default, float)


def env_bool(name: str, default: bool):
    return _env(name, default, _as_bool)


@dataclass(frozen=True)
class Settings:
    code: str = env_str("RMSP_CODE", "RMSP")
    name: str = env_str("RMSP_NAME", "São Paulo")
    description: str = env_str(
        "RMSP_DESCRIPTION",
        "Região Metropolitana de São Paulo com demanda real da "
        "Pesquisa Origem-Destino do Metrô-SP.",
    )
    population: int = env_int("RMSP_POPULATION", 22_800_000)  # Σ Censo 2022 no bbox (~22.8M)
    center_lat: float = env_float("RMSP_CENTER_LAT", -23.5505)  # Praça da Sé
    center_lng: float = env_float("RMSP_CENTER_LNG", -46.6333)
    zoom: float = env_float("RMSP_ZOOM", 9)  # abre enquadrando a RMSP inteira
    min_zoom: float = env_float("RMSP_MIN_ZOOM", 8)  # permite afastar até ver toda a região
    # Cobre todo o extent da Pesquisa OD 2023 (527 zonas) + ~1 km de margem: Embu (O) a Mogi
    # (L), Franco da Rocha (N) à borda da Billings (S). (min_lng, min_lat, max_lng, max_lat)
    bbox: tuple[float, float, float, float] = (-47.22, -24.08, -45.68, -23.17)
    # Worker processes for the buildings-index build pass. 0 = auto (all but one core).
    build_workers: int = env_int("RMSP_BUILD_WORKERS", 0)

    # Drop buildings below this footprint (m²); depot uses it as building_index_filter_size.
    # At ~120 m² the whole-RMSP index stays under the renderer's ~2 GB JSON heap.
    bldg_area_min_m2: float = env_float("RMSP_BLDG_AREA_MIN_M2", 120.0)
    # deg->m scale at ~lat -23.5, used by the straight-line routing metric (routing.py).
    m_per_deg_lat: float = env_float("RMSP_M_PER_DEG_LAT", 110900.0)
    m_per_deg_lng: float = env_float("RMSP_M_PER_DEG_LNG", 101900.0)
    # generate.py pre-drops buildings below this footprint (m²) before mapshaper (Overture's
    # ~7M tiny features OOM its -clean). A touch under bldg_area_min_m2 so mapshaper's own
    # filter still makes the final cut identically.
    bldg_prefilter_m2: float = env_float("RMSP_BLDG_PREFILTER_M2", 100.0)

    # depot MapGen inputs (non-demand: roads, buildings, airports, ocean, pmtiles)
    maxzoom: int = env_int("RMSP_MAXZOOM", 15)
    building_index_simplification: float = env_float("RMSP_BUILDING_SIMPLIFY_M", 1.0)
    create_building_foundations: bool = env_bool("RMSP_BUILDING_FOUNDATIONS", True)
    create_ocean_foundations: bool = env_bool("RMSP_OCEAN_FOUNDATIONS", True)
    # V8 heap (GB) for mapshaper's -clean on the ~1 GB pre-filtered buildings; depot's 4 OOMs.
    mapshaper_ram_gb: float = env_float("RMSP_MAPSHAPER_RAM_GB", 10.0)
    # Cap (KB) per building tile in the pmtiles; tippecanoe drops the smallest to stay under
    # it. depot 1.2.0+ defaults to no cap (None) — we keep the historical 450 KB. 0 disables.
    max_building_tile_kb: int = env_int("RMSP_MAX_BUILDING_TILE_KB", 450)
    label_cities: list[str] = field(default_factory=lambda: ["city", "town", "borough"])
    label_suburbs: list[str] = field(default_factory=lambda: ["suburb", "village"])
    label_neighborhoods: list[str] = field(
        default_factory=lambda: ["neighbourhood", "quarter", "hamlet", "locality"]
    )

    # Demand is generated in subway-builder-rmsp-demand-data and published as a release asset;
    # here we just download it (RMSP_DEMAND_URL pins a version).
    demand_release_url: str = env_str(
        "RMSP_DEMAND_URL",
        "https://github.com/roquerodrigo/subway-builder-rmsp-demand-data/releases/download/"
        "v1.0.0/demand_data.json.gz",
    )
    # Inject depot code-prefixed POIs (rmsp.specials.POIS) into demand_data.json before routing.
    special_demand: bool = env_bool("RMSP_SPECIAL_DEMAND", True)

    # 5000 is taken by macOS Control Center (AirPlay). OSRM calls are localhost-bound, so
    # over-subscribe the workers.
    osrm_port: int = env_int("RMSP_OSRM_PORT", 5050)
    route_workers: int = env_int("RMSP_ROUTE_WORKERS", 16)
    # Douglas-Peucker tolerance on the routed path (degrees). ~80 m keeps the road shape
    # readable; paired with OSRM overview=full so fidelity is controlled here.
    path_simplify_eps: float = env_float("RMSP_PATH_SIMPLIFY_EPS", 0.0008)
    # Skip OSRM and connect each pop's two points with a direct segment (distance from the
    # equirectangular metric, seconds from route_straight_speed_kmh). Near-instant, no geometry.
    route_straight_line: bool = env_bool("RMSP_ROUTE_STRAIGHT_LINE", False)
    route_straight_speed_kmh: float = env_float("RMSP_ROUTE_STRAIGHT_SPEED_KMH", 30.0)

    geofabrik_pbf_url: str = env_str(
        "RMSP_GEOFABRIK_PBF_URL",
        "https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf",
    )

    def n_build_workers(self) -> int:
        """Resolve :attr:`build_workers` (0 = all but one core, floor 1)."""
        return self.build_workers if self.build_workers > 0 else max(1, (os.cpu_count() or 2) - 1)

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"

    @property
    def build_dir(self) -> Path:
        return self.data_dir / "build"

    @property
    def tiles_dir(self) -> Path:
        return self.data_dir / "tiles"

    @property
    def dist_dir(self) -> Path:
        """Release artifacts (Railyard map .zip + Update JSON) — at the project root."""
        return PROJECT_ROOT / "dist"

    @property
    def logs_dir(self) -> Path:
        """Timestamped game-console logs from `rmsp debug` (gitignored)."""
        return PROJECT_ROOT / "logs"

    @property
    def pbf(self) -> Path:
        return self.sources_dir / "sudeste-latest.osm.pbf"

    @property
    def pbf_clip(self) -> Path:
        return self.sources_dir / "rmsp.osm.pbf"

    def ensure_dirs(self) -> None:
        for d in (self.sources_dir, self.build_dir, self.tiles_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
