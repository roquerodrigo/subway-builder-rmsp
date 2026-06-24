"""Single source of truth for the RMSP build: city params, tuning knobs, paths.

Every magic number lives here. Game install paths resolve from the ``SB_DATA_DIR``
environment variable (default: the macOS Subway Builder data dir), so the same
project can target a different copy of the game.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    # --- city ---
    code: str = "RMSP"
    name: str = "São Paulo (RMSP)"
    description: str = (
        "A maior metrópole do hemisfério sul. Mancha urbana central da Grande "
        "São Paulo — capital, ABC, Guarulhos, Osasco e Diadema — com ~17 mi de "
        "habitantes e ~8 mi de empregos. Demanda baseada na Pesquisa "
        "Origem-Destino do Metrô-SP."
    )
    population: int = 17_400_000
    center_lat: float = -23.5505  # Praça da Sé
    center_lng: float = -46.6333
    zoom: float = 11
    min_zoom: float = 9

    # Central urban mancha: capital + ABC + Guarulhos + Osasco/Barueri + Diadema.
    # (min_lng, min_lat, max_lng, max_lat)
    bbox: tuple[float, float, float, float] = (-46.85, -23.82, -46.36, -23.40)

    # spatial-grid cell size for buildings/water indexes (mirrors shipped cities)
    cell_size: float = 0.0009

    # --- buildings ---
    bldg_area_min_m2: float = 30.0  # drop sheds/garages below this
    bldg_simplify_tol: float = 9.0e-6  # ~1 m in degrees (Douglas-Peucker)
    bldg_decimals: int = 5
    bldg_max_floors: int = 80
    m_per_deg_lat: float = 110900.0  # at ~lat -23.5
    m_per_deg_lng: float = 101900.0

    # --- water (ocean_depth_index) ---
    water_deep_area_deg2: float = 1e-5  # bigger than this = reservoir (deeper)
    water_deep_depth: int = -10
    water_shallow_depth: int = -4

    # --- airports ---
    airport_half_width: dict[str, float] = field(
        default_factory=lambda: {"runway": 25.0, "taxiway": 12.0, "apron": 0.0}
    )
    airport_default_half_width: float = 10.0
    airport_min_buffer: float = 6.0
    metric_crs: str = "EPSG:31983"  # SIRGAS 2000 / UTM 23S, metres for buffering

    # --- demand (Pesquisa OD Metrô-SP) ---
    od_year: int = 2023  # 2023 or 2017 (same field layout/coding)
    min_pop_size: int = 15  # drop OD pairs below this many expanded trips
    home_motive: int = 8
    work_motives: frozenset[int] = frozenset({1, 2, 3})  # indústria/comércio/serviços
    edu_motives: frozenset[int] = frozenset({4})

    # --- routing (OSRM) ---
    osrm_port: int = 5050  # 5000 is taken by macOS Control Center (AirPlay)
    route_workers: int = 8
    path_simplify_eps: float = 0.002  # ~220 m, keeps road shape, light file

    # --- tiles ---
    tile_zoom_min: int = 8
    tile_zoom_max: int = 15
    foundation_zoom_min: int = 12
    tile_server_port: int = 8080

    # --- download URLs ---
    geofabrik_pbf_url: str = (
        "https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf"
    )
    od2023_zip_url: str = (
        "https://transparencia.metrosp.com.br/sites/default/files/Site_190225_PesquisaOD2023.zip"
    )
    od2017_zip_url: str = "https://transparencia.metrosp.com.br/sites/default/files/OD-2017.zip"

    # ---------- derived: bbox ----------
    @property
    def min_lng(self) -> float:
        return self.bbox[0]

    @property
    def min_lat(self) -> float:
        return self.bbox[1]

    @property
    def max_lng(self) -> float:
        return self.bbox[2]

    @property
    def max_lat(self) -> float:
        return self.bbox[3]

    def in_bbox(self, lng: float, lat: float) -> bool:
        return self.min_lng <= lng <= self.max_lng and self.min_lat <= lat <= self.max_lat

    @property
    def job_motives(self) -> frozenset[int]:
        return self.work_motives | self.edu_motives

    # ---------- derived: project paths ----------
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
    def pbf(self) -> Path:
        return self.sources_dir / "sudeste-latest.osm.pbf"

    @property
    def pbf_clip(self) -> Path:
        return self.sources_dir / "rmsp.osm.pbf"

    def od_paths(self) -> tuple[Path, Path]:
        """(zones shapefile base path, OD microdata .dbf) for the configured year."""
        if self.od_year == 2023:
            base = self.sources_dir / "od2023" / "Site_190225"
            return (
                base / "002_Site Metro Mapas_190225" / "Shape" / "Zonas_2023",
                base / "Banco2023_divulgacao_190225.dbf",
            )
        base = self.sources_dir / "od2017" / "OD-2017"
        return (
            base / "Mapas-OD2017" / "Shape-OD2017" / "Zonas_2017_region",
            base / "Banco de Dados-OD2017" / "OD_2017_v1.dbf",
        )

    # ---------- derived: game install targets ----------
    @property
    def game_dir(self) -> Path:
        return Path(
            os.environ.get(
                "SB_DATA_DIR",
                os.path.expanduser("~/Library/Application Support/metro-maker4"),
            )
        )

    @property
    def mod_dir(self) -> Path:
        return self.game_dir / "mods" / "rmsp"

    @property
    def mod_data(self) -> Path:
        return self.mod_dir / "data" / self.code

    @property
    def city_data(self) -> Path:
        return self.game_dir / "cities" / "data" / self.code

    def ensure_dirs(self) -> None:
        for d in (self.sources_dir, self.build_dir, self.tiles_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
