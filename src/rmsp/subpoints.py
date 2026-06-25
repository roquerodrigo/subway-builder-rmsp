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
from collections import defaultdict
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
    raw = props.get("building:levels")
    try:
        n = float(str(raw).split(";")[0])
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, min(float(settings.bldg_levels_cap), n))


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


def building_weight(props: dict, area_deg2: float) -> tuple[float, float]:
    """(residential_weight, job_weight) ≈ floor area (m²) split by use."""
    area_m2 = area_deg2 * settings.m_per_deg_lat * settings.m_per_deg_lng
    floor = area_m2 * _levels(props)
    res_f, job_f = classify(props)
    return floor * res_f, floor * job_f


def _cell(lng: float, lat: float) -> tuple[int, int]:
    cs = settings.subcell_size
    return (int((lng - settings.min_lng) / cs), int((lat - settings.min_lat) / cs))


def build_subpoints(zone_of) -> dict[int, list[SubPoint]]:
    """Stream buildings.geojsonseq → {zone_no: [SubPoint, ...]}.

    ``zone_of(lng, lat) -> int | None`` assigns a point to its OD zone.
    Buildings are aggregated by (zone, grid cell); each cell yields one
    sub-point at the floor-area-weighted centroid.
    """
    path = settings.sources_dir / "buildings.geojsonseq"
    # (zone, cell) -> [res_w, job_w, w*lng, w*lat, w]
    acc: dict[tuple[int, tuple[int, int]], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    n = kept = 0
    for ft in geojson.read_features(path):
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
        e = acc[(zone, _cell(clng, clat))]
        e[0] += res_w
        e[1] += job_w
        e[2] += w * clng
        e[3] += w * clat
        e[4] += w
        kept += 1
    log.info("buildings: scanned=%d kept=%d cells=%d", n, kept, len(acc))

    out: dict[int, list[SubPoint]] = defaultdict(list)
    for (zone, _cellkey), (res_w, job_w, wl, wt, w) in acc.items():
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
