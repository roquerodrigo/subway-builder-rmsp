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
        "Região Metropolitana de São Paulo inteira, com demanda real da "
        "Pesquisa Origem-Destino do Metrô-SP."
    )
    population: int = 22_800_000  # Σ Censo 2022 setor population within the map bbox (~22.8M)
    center_lat: float = -23.5505  # Praça da Sé
    center_lng: float = -46.6333
    zoom: float = 11
    min_zoom: float = 9

    # Full Pesquisa OD 2023 survey extent (all 527 zones) + ~1 km margin, so every
    # demand zone falls inside the rendered map. Embu/Itapecerica (W) to Mogi (E),
    # Franco da Rocha (N) to the Billings/coast edge (S). (min_lng, min_lat, max_lng, max_lat)
    bbox: tuple[float, float, float, float] = (-47.22, -24.08, -45.68, -23.17)

    # spatial-grid cell size for buildings/water indexes (mirrors shipped cities)
    cell_size: float = 0.0009

    # Worker processes for the per-feature build passes (buildings index + demand
    # sub-points). 0 = auto (all but one core). RMSP_BUILD_WORKERS overrides; 1
    # forces the in-process path (handy for profiling/debugging).
    build_workers: int = field(
        default_factory=lambda: int(os.environ.get("RMSP_BUILD_WORKERS", "0"))
    )

    # --- buildings ---
    # Drop buildings below this footprint. At ~120 m² the whole-RMSP buildings_index is
    # ~650k features (from ~1.9M at 30 m²), keeping the renderer's JSON heap well under
    # its ~2 GB limit — 1.9M building objects OOM-crashed the game on the full metro.
    bldg_area_min_m2: float = 120.0
    bldg_simplify_tol: float = 9.0e-6  # ~1 m in degrees (Douglas-Peucker)
    bldg_decimals: int = 5
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

    # --- demand (Pesquisa OD 2023 do Metrô-SP) ---
    min_pop_size: int = 20  # drop pops carrying fewer than this many commuters (cuts noise)
    home_motive: int = 8
    work_motives: frozenset[int] = frozenset({1, 2, 3})  # indústria/comércio/serviços
    edu_motives: frozenset[int] = frozenset({4})

    # --- demand: dasymetric disaggregation (zone totals -> sub-points) ---
    # The official OD survey fixes per-zone residents/jobs and the zone->zone matrix;
    # a proxy (see demand_proxy below) only decides *where inside a zone* demand sits.
    # residents_basis (RMSP_BASIS, eases A/B comparison):
    #   "workers" = FE_PESS per person, home (ZONA) -> workplace (ZONATRA1), ~10.4M.
    #   "commute" = FE_VIA home->work/edu trip marginals (smaller spatial spread).
    residents_basis: str = field(default_factory=lambda: os.environ.get("RMSP_BASIS", "workers"))
    # Which proxy decides *where inside a zone* demand sits (the OD survey still fixes the
    # per-zone totals either way): "buildings" = OSM footprint floor-area heuristic;
    # "cnefe" = IBGE Censo 2022 georeferenced address points (finer, real res/job split).
    # RMSP_DEMAND_PROXY overrides. "cnefe" needs `rmsp sources` to have built cnefe.csv.
    demand_proxy: str = field(
        default_factory=lambda: os.environ.get("RMSP_DEMAND_PROXY", "cnefe")
    )
    subcell_size: float = 0.0098  # ~1 km grid inside each zone for sub-points (consolidated)
    subpoint_min_weight: float = 1.0  # drop near-empty cells
    dest_cap: int = 8  # top destination zones kept per origin (bounds pop count)
    bldg_levels_cap: int = 60  # clamp building:levels outliers (floor-area proxy)
    # building:levels is tagged on <1% of RMSP buildings but `height` on ~95%;
    # fall back to height ÷ this (m/floor) so vertical density drives the weight.
    meters_per_floor: float = 3.2
    # OSM height aliases tried in order before the typology-default fallback.
    height_tag_keys: tuple[str, ...] = ("height", "building:height", "est_height")
    mixed_use_split: tuple[float, float] = (0.5, 0.5)  # unknown buildings: (res, job)
    # Per-m² density multipliers by building= class, applied on top of floor area so
    # a tower of flats concentrates more residents per m² than a same-area house, and
    # an office more jobs per m² than a warehouse. Only intra-zone ratios matter
    # (weights are normalized per zone in demand.py), so absolute values are free.
    density_mult_default: float = 1.0  # building=yes / unlisted classes: unchanged
    res_density_mult: dict[str, float] = field(
        default_factory=lambda: {
            "dormitory": 4.0, "apartments": 3.0, "residential": 1.5, "terrace": 1.2,
            "house": 1.0, "detached": 1.0, "semidetached_house": 1.0,
            "hut": 0.4, "cabin": 0.4, "static_caravan": 0.4,
        }
    )
    job_density_mult: dict[str, float] = field(
        default_factory=lambda: {
            "office": 2.5, "commercial": 2.0, "retail": 1.8, "supermarket": 1.8,
            "mall": 1.8, "hospital": 1.5, "school": 1.2, "university": 1.2,
            "industrial": 0.5, "warehouse": 0.3, "hangar": 0.2, "depot": 0.2,
        }
    )
    # Default floor count when neither building:levels nor a height tag is present,
    # by building= class — keeps untagged flats/offices from collapsing to one storey.
    typology_default_levels: dict[str, float] = field(
        default_factory=lambda: {
            "apartments": 6.0, "hotel": 5.0, "office": 4.0, "hospital": 4.0,
            "residential": 3.0, "commercial": 2.0, "retail": 2.0,
        }
    )

    # --- demand: CNEFE 2022 address-point proxy (when demand_proxy == "cnefe") ---
    # IBGE Censo 2022 CNEFE has lat/lng per address + COD_ESPECIE (1=domicílio particular,
    # 2=domicílio coletivo, 3-6/8=estabelecimentos, 7=edificação em construção). Since
    # weights are normalized per zone, address *density* per cell is the weight directly —
    # no floor-area heuristic. NV_GEO_COORD is the coordinate-quality level (1=address door,
    # higher=coarser face/block/sector centroid).
    cnefe_res_especies: frozenset[int] = frozenset({1, 2})  # housing
    cnefe_job_especies: frozenset[int] = frozenset({3, 4, 5, 6, 8})  # establishments
    cnefe_skip_especies: frozenset[int] = frozenset({7})  # under construction
    # Per-espécie weight (e.g. a collective dwelling counts heavier than one household);
    # unlisted espécies default to 1.0.
    cnefe_especie_weight: dict[int, float] = field(default_factory=lambda: {2: 3.0})
    # Accept these NV_GEO_COORD levels; None = accept all. Coarser-than-block geocoding
    # still lands inside the ~1 km sub-cells, so keep all by default.
    cnefe_coord_levels: frozenset[int] | None = None
    # Refine residential placement with real per-setor population (Censo 2022 "Agregados
    # por setores", variable v0001): each setor's population is spread across its CNEFE
    # residential addresses (res_w = pop / address_count), so dense setores outweigh
    # sparse ones inside a zone instead of every address counting the same. RMSP_CNEFE_CENSUS=0
    # disables it (falls back to per-espécie weights). The setor code joins CNEFE COD_SETOR
    # (15 digits + a 1-char situation suffix that is stripped) to census CD_SETOR.
    censo_use_pop_weight: bool = field(
        default_factory=lambda: os.environ.get("RMSP_CNEFE_CENSUS", "1") not in {"0", "false", "no"}
    )
    censo_basico_url: str = (
        "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
        "Agregados_por_Setor_csv/Agregados_por_setores_basico_BR_20260520.zip"
    )
    # Cap on a residential address's census weight (persons/address). A setor with real
    # population but very few CNEFE residential addresses (boundary/coding artifact) would
    # otherwise dump hundreds of residents onto one point; clamp to a generous household
    # size so such cases stay bounded without affecting the ~99% in normal range.
    cnefe_max_addr_weight: float = 50.0

    # --- routing (OSRM) ---
    osrm_port: int = 5050  # 5000 is taken by macOS Control Center (AirPlay)
    route_workers: int = 16  # OSRM client calls are localhost I/O-bound, so over-subscribe
    # Douglas-Peucker tolerance on the routed path (degrees). ~80 m keeps the road shape
    # readable (the old 220 m straightened curves into polygons) at ~2× the file size;
    # paired with OSRM overview=full so we control fidelity here rather than inheriting
    # OSRM's coarse cut. Lower toward 0.0005 (~50 m) for max fidelity / bigger file.
    path_simplify_eps: float = 0.0008

    # --- tiles ---
    tile_zoom_min: int = 8
    tile_zoom_max: int = 15
    foundation_zoom_min: int = 12
    tile_server_port: int = 8080

    # --- download URLs ---
    geofabrik_pbf_url: str = (
        "https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf"
    )
    od_zip_url: str = (
        "https://transparencia.metrosp.com.br/sites/default/files/Site_190225_PesquisaOD2023.zip"
    )
    # IBGE Censo 2022 CNEFE, São Paulo state (UF 35) — ~1 GB zip of per-address CSV.
    cnefe_url: str = (
        "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
        "Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/35_SP.zip"
    )

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

    def n_build_workers(self) -> int:
        """Resolve :attr:`build_workers` (0 = all but one core, floor 1)."""
        return self.build_workers if self.build_workers > 0 else max(1, (os.cpu_count() or 2) - 1)

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
    def logs_dir(self) -> Path:
        return PROJECT_ROOT / "logs"

    @property
    def pbf(self) -> Path:
        return self.sources_dir / "sudeste-latest.osm.pbf"

    @property
    def pbf_clip(self) -> Path:
        return self.sources_dir / "rmsp.osm.pbf"

    @property
    def cnefe_zip(self) -> Path:
        return self.sources_dir / "35_SP.zip"

    @property
    def cnefe_csv(self) -> Path:
        """Compact bbox-filtered CNEFE points: ``lng,lat,especie,setor`` per line (no header)."""
        return self.sources_dir / "cnefe.csv"

    @property
    def censo_basico_zip(self) -> Path:
        return self.sources_dir / "censo_basico_BR.zip"

    @property
    def setor_pop_csv(self) -> Path:
        """Per-setor Censo 2022 population (``setor,pop`` per line) for residential weighting."""
        return self.sources_dir / "setor_pop.csv"

    @property
    def od_dir(self) -> Path:
        return self.sources_dir / "od2023"

    @property
    def od_zip(self) -> Path:
        return self.sources_dir / "od2023.zip"

    def od_paths(self) -> tuple[Path, Path]:
        """(zones shapefile base path, OD microdata .dbf) from the Pesquisa OD 2023."""
        base = self.od_dir / "Site_190225"
        return (
            base / "002_Site Metro Mapas_190225" / "Shape" / "Zonas_2023",
            base / "Banco2023_divulgacao_190225.dbf",
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
    def city_data(self) -> Path:
        return self.game_dir / "cities" / "data" / self.code

    def ensure_dirs(self) -> None:
        for d in (self.sources_dir, self.build_dir, self.tiles_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
