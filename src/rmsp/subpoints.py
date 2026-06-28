"""Turn OSM buildings into per-zone demand sub-points (dasymetric disaggregation).

The official OD survey fixes how *much* residential/job demand each OD zone has;
this module decides *where inside the zone* it sits, by weighting OSM building
footprint floor area (area × levels) split into a residential and a job share
from the building's tags. Buildings are bucketed into a fine grid within their
zone, and each non-empty cell becomes one demand sub-point at its weighted
centroid. Nothing here alters official magnitudes.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

# OSM building= values that are unambiguously housing.
RESIDENTIAL_BUILDINGS = frozenset(
    {
        "residential", "apartments", "house", "detached", "semidetached_house",
        "terrace", "dormitory", "bungalow", "cabin", "hut", "farm", "houseboat",
        "static_caravan", "ger", "stilt_house",
    }
)
# OSM building= values that are unambiguously workplaces / activity sites.
JOB_BUILDINGS = frozenset(
    {
        "commercial", "office", "retail", "industrial", "warehouse", "supermarket",
        "kiosk", "hotel", "hospital", "clinic", "school", "university", "college",
        "government", "public", "civic", "factory", "manufacture", "hangar",
        "depot", "transportation", "train_station", "stadium", "sports_centre",
        "mall", "shop",
    }
)
# amenity values that do NOT imply a workplace (ignore as job signal).
_NON_JOB_AMENITIES = frozenset(
    {"parking", "parking_space", "bicycle_parking", "bench", "waste_basket",
     "shelter", "fountain", "drinking_water", "toilets"}
)
_JOB_TAG_KEYS = ("shop", "office", "tourism", "craft", "healthcare")


@dataclass(frozen=True, slots=True)
class SubPoint:
    id: str
    lng: float
    lat: float
    res_w: float
    job_w: float


def _has_job_signal(props: dict) -> bool:
    if any(props.get(k) for k in _JOB_TAG_KEYS):
        return True
    am = props.get("amenity")
    return bool(am) and am not in _NON_JOB_AMENITIES


def classify(props: dict) -> tuple[float, float]:
    """Return (residential_fraction, job_fraction), summing to 1, from OSM tags."""
    b = (props.get("building") or "").lower()
    job = _has_job_signal(props)
    if b in RESIDENTIAL_BUILDINGS:
        return (0.8, 0.2) if job else (1.0, 0.0)
    if b in JOB_BUILDINGS:
        return (0.0, 1.0)
    # building=yes / unknown: a shop/office/amenity makes it a workplace,
    # otherwise fall back to the configured mixed-use split.
    return (0.0, 1.0) if job else settings.mixed_use_split


def _levels(props: dict) -> float:
    """Above-ground floor count — the vertical-density multiplier on footprint area.

    Prefer the explicit ``building:levels``; in RMSP OSM it is tagged on <1% of
    buildings, so fall back to a height tag (``height``/``building:height``/
    ``est_height``, ≈95% coverage) ÷ floor height. Without either, use a per-typology
    default (untagged flats/offices are clearly multi-storey) and otherwise a single
    storey. Clamped to ``bldg_levels_cap`` so a tower outweighs a same-footprint house
    instead of tying with it.
    """
    cap = float(settings.bldg_levels_cap)
    raw = props.get("building:levels")
    if raw is not None:
        try:
            return max(1.0, min(cap, float(str(raw).split(";")[0])))
        except (TypeError, ValueError):
            pass
    for key in settings.height_tag_keys:
        h = props.get(key)
        if h is None:
            continue
        try:
            metres = float(str(h).split(";")[0].replace("m", "").strip())
            return max(1.0, min(cap, metres / settings.meters_per_floor))
        except (TypeError, ValueError):
            pass
    b = (props.get("building") or "").lower()
    return max(1.0, min(cap, settings.typology_default_levels.get(b, 1.0)))


def _ring_area_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    """Shoelace |area| (deg²) and centroid (lng, lat) of a polygon ring."""
    n = len(ring)
    if n < 3:
        return 0.0, 0.0, 0.0
    a = cx = cy = 0.0
    for i in range(n - 1):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[i + 1][0], ring[i + 1][1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return 0.0, sum(xs) / n, sum(ys) / n
    return abs(a) / 2.0, cx / (3.0 * a), cy / (3.0 * a)


def _density_mult(b: str) -> tuple[float, float]:
    """(res_mult, job_mult) per-m² density multipliers for a ``building=`` class.

    Unlisted classes (incl. ``building=yes``) keep ``density_mult_default`` so the
    weight stays raw floor area; only listed typologies are scaled relative to it.
    """
    d = settings.density_mult_default
    return settings.res_density_mult.get(b, d), settings.job_density_mult.get(b, d)


def building_weight(props: dict, area_deg2: float) -> tuple[float, float]:
    """(residential_weight, job_weight) ≈ floor area (m²) split by use, then scaled
    by a per-typology density so towers/offices concentrate more per m² than
    houses/warehouses. Intra-zone normalization in demand.py makes the absolute
    scale irrelevant — only the ratios between same-zone sub-points matter."""
    area_m2 = area_deg2 * settings.m_per_deg_lat * settings.m_per_deg_lng
    floor = area_m2 * _levels(props)
    res_f, job_f = classify(props)
    res_m, job_m = _density_mult((props.get("building") or "").lower())
    return floor * res_f * res_m, floor * job_f * job_m


def _cell(lng: float, lat: float) -> tuple[int, int]:
    cs = settings.subcell_size
    return (int((lng - settings.min_lng) / cs), int((lat - settings.min_lat) / cs))


def _subpoints_chunk(path, start: int, end: int, zones_shp: Path) -> dict:
    """Aggregate one byte-range of buildings.geojsonseq into {(zone, cell): acc}.

    Each worker rebuilds its own zone index (the STRtree can't cross a process
    boundary, and load_zone_index is ~0.4 s vs. the per-building point-in-polygon
    cost this parallelizes). Returns a plain dict (no lambda) so it pickles back to
    :func:`build_subpoints`, which sums partials. Top-level for ProcessPool pickling.
    """
    zone_of, _ = load_zone_index(zones_shp)
    acc: dict[tuple[int, tuple[int, int]], list[float]] = {}
    n = kept = 0
    for ft in geojson.read_features_range(path, start, end):
        n += 1
        rings = geojson.outer_rings(ft.get("geometry") or {})
        if not rings:
            continue
        props = ft.get("properties") or {}
        area = clng = clat = 0.0
        for ring in rings:  # area-weighted centroid across (multi)polygon parts
            ra, rx, ry = _ring_area_centroid(ring)
            area += ra
            clng += rx * ra
            clat += ry * ra
        if area <= 0:
            continue
        clng, clat = clng / area, clat / area
        if (area * settings.m_per_deg_lat * settings.m_per_deg_lng) < settings.bldg_area_min_m2:
            continue
        zone = zone_of(clng, clat)
        if zone is None:
            continue
        res_w, job_w = building_weight(props, area)
        w = res_w + job_w
        if w <= 0:
            continue
        key = (zone, _cell(clng, clat))
        e = acc.get(key)
        if e is None:
            e = acc[key] = [0.0, 0.0, 0.0, 0.0, 0.0]
        e[0] += res_w
        e[1] += job_w
        e[2] += w * clng
        e[3] += w * clat
        e[4] += w
        kept += 1
    log.info("buildings chunk [%d,%d): scanned=%d kept=%d cells=%d", start, end, n, kept, len(acc))
    return acc


def _cnefe_classify(especie: int) -> tuple[float, float]:
    """(res_w, job_w) for one CNEFE address from its COD_ESPECIE (housing vs establishment).

    Used for jobs always, and for housing when census weighting is off; with census
    weighting on, residential weight comes from the per-setor population instead."""
    w = settings.cnefe_especie_weight.get(especie, 1.0)
    if especie in settings.cnefe_res_especies:
        return w, 0.0
    if especie in settings.cnefe_job_especies:
        return 0.0, w
    return 0.0, 0.0  # skipped espécies (e.g. under construction)


def _cnefe_weights() -> tuple[dict[str, float] | None, float]:
    """(setor → per-residential-address weight, global fallback weight).

    Spreads each setor's Censo 2022 population across its CNEFE residential addresses
    (``res_w = pop / address_count``), so res_w sums to the real population per setor.
    The fallback (Σpop/Σcount over matched setores ≈ mean household size) is used for
    addresses whose setor is missing from the census. Returns ``(None, 0.0)`` when census
    weighting is disabled or the data is absent — callers then fall back to espécie weights.
    """
    if not settings.censo_use_pop_weight or not settings.setor_pop_csv.exists():
        return None, 0.0
    pop: dict[str, float] = {}
    with open(settings.setor_pop_csv, encoding="ascii") as f:
        for line in f:
            s, p = line.rstrip("\n").split(",")
            pop[s] = float(p)
    res_count: Counter[str] = Counter()  # CNEFE residential addresses per setor
    res_especies = settings.cnefe_res_especies
    with open(settings.cnefe_csv, "rb") as f:
        for raw in f:
            parts = raw.rstrip(b"\n").split(b",")
            if len(parts) != 4:
                continue
            try:
                especie = int(parts[2])
            except ValueError:
                continue
            if especie in res_especies:
                res_count[parts[3].decode()] += 1
    cap = settings.cnefe_max_addr_weight
    raw = {s: pop[s] / c for s, c in res_count.items() if s in pop and c > 0}
    weights = {s: min(w, cap) for s, w in raw.items()}
    clipped = sum(1 for w in raw.values() if w > cap)
    tot_pop = sum(pop[s] for s in weights)
    tot_cnt = sum(res_count[s] for s in weights)
    default_w = min(cap, tot_pop / tot_cnt) if tot_cnt else 1.0
    log.info(
        "census weights: setores=%d cnefe-res=%d matched=%d clipped@%.0f=%d default_w=%.2f",
        len(pop), len(res_count), len(weights), cap, clipped, default_w,
    )
    return weights, default_w


def _cnefe_chunk(
    path, start: int, end: int, zones_shp: Path,
    weights: dict[str, float] | None = None, default_w: float = 0.0,
) -> dict:
    """Aggregate one byte-range of cnefe.csv (``lng,lat,especie,setor`` lines) into
    {(zone, cell): acc}. The address-point analogue of :func:`_subpoints_chunk`: each
    address contributes its weight at its own coordinate (no geometry/area math).
    When ``weights`` is given, residential weight is the per-setor census share; jobs
    always use the espécie weight. Top-level for ProcessPool pickling."""
    zone_of, _ = load_zone_index(zones_shp)
    res_especies = settings.cnefe_res_especies
    acc: dict[tuple[int, tuple[int, int]], list[float]] = {}
    n = kept = 0
    for raw in geojson.read_lines_range(path, start, end):
        n += 1
        try:
            slng, slat, sesp, ssetor = raw.split(b",")
            lng, lat, especie = float(slng), float(slat), int(sesp)
        except ValueError:
            continue
        if weights is not None and especie in res_especies:
            res_w, job_w = weights.get(ssetor.decode(), default_w), 0.0
        else:
            res_w, job_w = _cnefe_classify(especie)
        w = res_w + job_w
        if w <= 0:
            continue
        zone = zone_of(lng, lat)
        if zone is None:
            continue
        key = (zone, _cell(lng, lat))
        e = acc.get(key)
        if e is None:
            e = acc[key] = [0.0, 0.0, 0.0, 0.0, 0.0]
        e[0] += res_w
        e[1] += job_w
        e[2] += w * lng
        e[3] += w * lat
        e[4] += w
        kept += 1
    log.info("cnefe chunk [%d,%d): scanned=%d kept=%d cells=%d", start, end, n, kept, len(acc))
    return acc


def build_subpoints(zones_shp: Path) -> dict[int, list[SubPoint]]:
    """Stream the configured demand proxy → {zone_no: [SubPoint, ...]}.

    ``settings.demand_proxy`` selects the source (OSM building footprints or CNEFE
    address points); either way features are aggregated by (zone, grid cell) across
    worker processes (each rebuilding the zone index from ``zones_shp``) and the partial
    accumulators are summed here, so the result is independent of the chunking.
    """
    if settings.demand_proxy == "cnefe":
        path = settings.cnefe_csv
        worker, extra = _cnefe_chunk, (zones_shp, *_cnefe_weights())
    else:
        path = settings.sources_dir / "buildings.geojsonseq"
        worker, extra = _subpoints_chunk, (zones_shp,)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} missing for demand_proxy={settings.demand_proxy!r}; run `rmsp sources`"
        )
    parts = geojson.parallel_chunks(path, worker, settings.n_build_workers(), *extra)
    return _merge_subpoints(parts)


def _merge_subpoints(parts: list[dict]) -> dict[int, list[SubPoint]]:
    """Sum partial (zone, cell) accumulators and emit one SubPoint per cell at its
    weighted centroid. Sorted by key so ids/output are deterministic across chunkings."""
    # (zone, cell) -> [res_w, job_w, w*lng, w*lat, w]
    acc: dict[tuple[int, tuple[int, int]], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    for part in parts:
        for key, (res_w, job_w, wl, wt, w) in part.items():
            e = acc[key]
            e[0] += res_w
            e[1] += job_w
            e[2] += wl
            e[3] += wt
            e[4] += w
    log.info("subpoints: cells=%d", len(acc))

    out: dict[int, list[SubPoint]] = defaultdict(list)
    for (zone, _cellkey), (res_w, job_w, wl, wt, w) in sorted(acc.items()):
        if w < settings.subpoint_min_weight:
            continue
        sp = SubPoint(
            id=f"z{zone}c{len(out[zone])}",
            lng=round(wl / w, 5),
            lat=round(wt / w, 5),
            res_w=res_w,
            job_w=job_w,
        )
        out[zone].append(sp)
    return out


def load_zone_index(zones_shp: Path):
    """Return (zone_of, centroids) where zone_of(lng,lat)->zone_no|None and
    centroids is {zone_no: (lng, lat, name)} — using an STRtree over zone polys."""
    import shapefile
    import shapely
    from pyproj import CRS, Transformer
    from shapely import STRtree
    from shapely.geometry import shape as shp_shape
    from shapely.ops import transform as shp_transform

    to_wgs = Transformer.from_crs(
        CRS.from_wkt(zones_shp.with_suffix(".prj").read_text()), "EPSG:4326", always_xy=True
    ).transform
    sf = shapefile.Reader(str(zones_shp), encoding="latin-1")
    flds = [f[0] for f in sf.fields[1:]]
    geoms: list = []
    zone_nos: list[int] = []
    centroids: dict[int, tuple[float, float, str]] = {}
    for sr in sf.iterShapeRecords():
        rec = dict(zip(flds, sr.record, strict=False))
        try:
            g = shp_transform(to_wgs, shp_shape(sr.shape.__geo_interface__))
            c = g.centroid
        except Exception:
            continue
        zn = int(rec["NumeroZona"])
        geoms.append(g)
        zone_nos.append(zn)
        centroids[zn] = (round(c.x, 5), round(c.y, 5), rec.get("NomeZona") or str(zn))
    tree = STRtree(geoms)

    def zone_of(lng: float, lat: float) -> int | None:
        pt = shapely.points(lng, lat)
        hits = tree.query(pt, predicate="within")
        return zone_nos[int(hits[0])] if len(hits) else None

    return zone_of, centroids
