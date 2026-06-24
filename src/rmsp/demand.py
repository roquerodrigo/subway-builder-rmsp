"""Build demand_data.json(.gz) from the real Pesquisa Origem-Destino (Metrô-SP).

points: one per OD zone whose centroid falls inside the bbox, with real residents
        (sum of person expansion FE_PESS by home zone) and jobs (by workplace zone).
pops:   home-based work/education trips aggregated by (origin, dest) zone, listed
        on BOTH endpoints' popIds (else the Workers tab has no arrival/departure).
        drivingPath starts as a straight line; routing.py replaces it with roads.
"""

from __future__ import annotations

import collections
import logging
import math
from pathlib import Path

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)


def _as_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _haversine_m(lng1, lat1, lng2, lat2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _speed_kmh(km: float) -> float:
    if km < 6:
        return 18.0
    if km < 15:
        return 26.0
    if km < 30:
        return 38.0
    return 48.0


def _zone_centroids(zones_shp: Path) -> dict[int, tuple[float, float, str]]:
    """zone number -> (lng, lat, name) for zones whose centroid is in the bbox."""
    import shapefile
    from pyproj import CRS, Transformer
    from shapely.geometry import shape as shp_shape

    to_wgs = Transformer.from_crs(
        CRS.from_wkt(zones_shp.with_suffix(".prj").read_text()), "EPSG:4326", always_xy=True
    ).transform
    sf = shapefile.Reader(str(zones_shp), encoding="latin-1")
    flds = [f[0] for f in sf.fields[1:]]
    zones: dict[int, tuple[float, float, str]] = {}
    for sr in sf.iterShapeRecords():
        rec = dict(zip(flds, sr.record, strict=False))
        try:
            c = shp_shape(sr.shape.__geo_interface__).centroid
            lng, lat = to_wgs(c.x, c.y)
        except Exception:
            continue
        if settings.in_bbox(lng, lat):
            zones[int(rec["NumeroZona"])] = (
                round(lng, 5),
                round(lat, 5),
                rec.get("NomeZona") or str(rec["NumeroZona"]),
            )
    return zones


def build_demand() -> None:
    from dbfread import DBF

    zones_shp, od_dbf = settings.od_paths()
    zones = _zone_centroids(zones_shp)
    log.info("zones in bbox: %d", len(zones))

    residents: dict[int, float] = collections.defaultdict(float)
    jobs: dict[int, float] = collections.defaultdict(float)
    seen_person: set = set()
    od: dict[tuple[int, int], list[float]] = collections.defaultdict(lambda: [0.0, 0.0, 0.0])

    nrows = 0
    for r in DBF(str(od_dbf), encoding="latin-1", raw=False):
        nrows += 1
        pkey = (r.get("ID_DOM"), r.get("ID_FAM"), r.get("ID_PESS"))
        if pkey not in seen_person:
            seen_person.add(pkey)
            fp = r.get("FE_PESS") or 0.0
            if fp:
                if (hz := _as_int(r.get("ZONA"))) in zones:
                    residents[hz] += fp
                if (wz := _as_int(r.get("ZONATRA1"))) in zones:
                    jobs[wz] += fp
        fv = r.get("FE_VIA") or 0.0
        if not fv:
            continue
        if _as_int(r.get("MOTIVO_O")) != settings.home_motive:
            continue
        if _as_int(r.get("MOTIVO_D")) not in settings.job_motives:
            continue
        o, d = _as_int(r.get("ZONA_O")), _as_int(r.get("ZONA_D"))
        if o is None or d is None or o == d or o not in zones or d not in zones:
            continue
        e = od[(o, d)]
        e[0] += fv
        e[1] += (r.get("DISTANCIA") or 0.0) * fv
        e[2] += (r.get("DURACAO") or 0.0) * fv

    log.info("rows=%d persons=%d od-pairs=%d", nrows, len(seen_person), len(od))

    points = [
        {
            "id": f"z{z}",
            "location": [lng, lat],
            "jobs": round(jobs.get(z, 0.0)),
            "residents": round(residents.get(z, 0.0)),
            "popIds": [],
        }
        for z, (lng, lat, _name) in sorted(zones.items())
    ]
    by_id = {p["id"]: p for p in points}

    pops = []
    total = 0
    for seq, ((o, d), (size_f, distw, durw)) in enumerate(od.items(), 1):
        size = round(size_f)
        if size < settings.min_pop_size:
            continue
        olng, olat, _ = zones[o]
        dlng, dlat, _ = zones[d]
        dist_m = distw / size_f if size_f else 0.0
        if dist_m < 100:
            dist_m = max(300.0, _haversine_m(olng, olat, dlng, dlat) * 1.42)
        dur_min = durw / size_f if size_f else 0.0
        secs = (
            round(dur_min * 60)
            if dur_min > 0
            else round(dist_m / (_speed_kmh(dist_m / 1000) * 1000 / 3600))
        )
        pid = f"p{seq:05d}"
        pops.append(
            {
                "id": pid,
                "size": size,
                "residenceId": f"z{o}",
                "jobId": f"z{d}",
                "drivingSeconds": secs,
                "drivingDistance": round(dist_m),
                "drivingPath": [[olng, olat], [dlng, dlat]],
            }
        )
        by_id[f"z{o}"]["popIds"].append(pid)
        by_id[f"z{d}"]["popIds"].append(pid)
        total += size

    demand = {"points": points, "pops": pops}
    geojson.write_json(demand, settings.build_dir / "demand_data.json")
    out = settings.build_dir / "demand_data.json.gz"
    geojson.write_json_gz(demand, out)
    log.info(
        "points=%d pops=%d commuters=%d residents=%d jobs=%d -> %s (%.2f MB)",
        len(points),
        len(pops),
        total,
        round(sum(residents.values())),
        round(sum(jobs.values())),
        out.name,
        geojson.mb(out),
    )
