"""Build demand_data.json(.gz) from the real Pesquisa Origem-Destino (Metrô-SP).

The official OD survey fixes the per-zone totals and the zone→zone matrix; OSM
buildings (via :mod:`rmsp.subpoints`) only decide *where inside a zone* demand
sits. Each commuter relationship becomes a pop from a residential sub-point to a
job sub-point; ``points`` are those sub-points. residents/jobs are derived from
the pops, so ``Σ residents == Σ jobs == Σ pop.size`` holds exactly (the game /
Railyard invariant).

Two bases (``settings.residents_basis``), both respecting the official survey:
  workers  – FE_PESS per person, home zone (ZONA) → workplace zone (ZONATRA1);
             totals = the working population (~9M).
  commute  – FE_VIA home→work/education trips by (ZONA_O, ZONA_D); totals = the
             expanded commute-trip volume (~7.7M).
"""

from __future__ import annotations

import collections
import logging
import math

from rmsp import geojson, subpoints
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


def _largest_remainder(weights: list[float], total: int) -> list[int]:
    """Apportion ``total`` integer units across ``weights`` (sum preserved)."""
    s = sum(weights)
    if s <= 0 or total <= 0:
        return [0] * len(weights)
    raw = [w / s * total for w in weights]
    out = [int(x) for x in raw]
    rem = total - sum(out)
    for i in sorted(range(len(weights)), key=lambda i: raw[i] - out[i], reverse=True)[:rem]:
        out[i] += 1
    return out


# ---------------------------------------------------------------- OD matrices
def _workers_od(zones: set[int]) -> dict[tuple[int, int], float]:
    """FE_PESS per person: home (ZONA) → workplace (ZONATRA1). Deduped by person."""
    from dbfread import DBF

    _, od_dbf = settings.od_paths()
    flows: dict[tuple[int, int], float] = collections.defaultdict(float)
    seen: set[tuple] = set()
    for r in DBF(str(od_dbf), encoding="latin-1", raw=False):
        key = (r.get("ID_DOM"), r.get("ID_FAM"), r.get("ID_PESS"))
        if key in seen:
            continue
        seen.add(key)
        fp = r.get("FE_PESS") or 0.0
        if not fp:
            continue
        hz, wz = _as_int(r.get("ZONA")), _as_int(r.get("ZONATRA1"))
        if hz in zones and wz in zones:  # intra-zone (hz==wz) is real local demand
            flows[(hz, wz)] += fp
    return flows


def _commute_od(zones: set[int]) -> dict[tuple[int, int], float]:
    """FE_VIA home→work/education trips aggregated by (origin, dest) zone."""
    from dbfread import DBF

    _, od_dbf = settings.od_paths()
    flows: dict[tuple[int, int], float] = collections.defaultdict(float)
    for r in DBF(str(od_dbf), encoding="latin-1", raw=False):
        fv = r.get("FE_VIA") or 0.0
        if not fv:
            continue
        if _as_int(r.get("MOTIVO_O")) != settings.home_motive:
            continue
        if _as_int(r.get("MOTIVO_D")) not in settings.job_motives:
            continue
        o, d = _as_int(r.get("ZONA_O")), _as_int(r.get("ZONA_D"))
        if o in zones and d in zones:  # intra-zone (o==d) is real local demand
            flows[(o, d)] += fv
    return flows


def _roulette(subs: list[subpoints.SubPoint], length: int = 64) -> list[int]:
    """Indices into ``subs`` repeated ∝ job_w, so round-robin picks spread jobs."""
    counts = _largest_remainder([s.job_w for s in subs], max(length, len(subs)))
    seq = [i for i, c in enumerate(counts) for _ in range(c)]
    return seq or list(range(len(subs)))


def _drive(o: subpoints.SubPoint, d: subpoints.SubPoint) -> tuple[int, int]:
    dist_m = max(300.0, _haversine_m(o.lng, o.lat, d.lng, d.lat) * 1.42)
    secs = round(dist_m / (_speed_kmh(dist_m / 1000) * 1000 / 3600))
    return secs, round(dist_m)


def build_demand() -> None:
    zones_shp, _ = settings.od_paths()
    _, centroids = subpoints.load_zone_index(zones_shp)
    zones = set(centroids)
    log.info("zones: %d", len(zones))

    subs = subpoints.build_subpoints(zones_shp)
    flows = _workers_od(zones) if settings.residents_basis == "workers" else _commute_od(zones)
    log.info(
        "basis=%s od-pairs=%d Σflow=%.0f",
        settings.residents_basis,
        len(flows),
        sum(flows.values()),
    )

    out_by_o: dict[int, list[tuple[int, float]]] = collections.defaultdict(list)
    for (o, d), v in flows.items():
        out_by_o[o].append((d, v))
    roulette: dict[int, list[int]] = {}
    rcount: dict[int, int] = collections.defaultdict(int)

    def _ensure_sub(z: int) -> list[subpoints.SubPoint]:
        """Zones with no usable buildings fall back to a single centroid sub-point."""
        if subs.get(z):
            return subs[z]
        lng, lat, _ = centroids[z]
        subs[z] = [subpoints.SubPoint(id=f"z{z}c0", lng=lng, lat=lat, res_w=1.0, job_w=1.0)]
        return subs[z]

    pops: list[dict] = []
    residents: dict[str, int] = collections.defaultdict(int)
    jobs: dict[str, int] = collections.defaultdict(int)
    point_by_id: dict[str, subpoints.SubPoint] = {}
    seq = 0

    for o, dests in out_by_o.items():
        all_o = _ensure_sub(o)
        osubs = [s for s in all_o if s.res_w > 0] or all_o
        res_zone = sum(v for _, v in dests)
        if res_zone <= 0:
            continue
        dests.sort(key=lambda x: x[1], reverse=True)
        kept = dests[: settings.dest_cap]
        kept_sum = sum(v for _, v in kept) or 1.0
        ow_sum = sum(s.res_w for s in osubs) or 1.0

        alloc: list[tuple[subpoints.SubPoint, subpoints.SubPoint, float]] = []
        for os in osubs:
            r_os = res_zone * (os.res_w / ow_sum)
            for d, fv in kept:
                dsubs = _ensure_sub(d)
                if d not in roulette:
                    roulette[d] = _roulette(dsubs)
                rseq = roulette[d]
                ds = dsubs[rseq[rcount[d] % len(rseq)]]
                rcount[d] += 1
                if ds.id == os.id and len(dsubs) > 1:
                    # never start and end a commute at the same point (intra-zone):
                    # advance the roulette to a different sub-point, keeping the
                    # job-weighted spread; if it only ever yields os, fall back to the
                    # heaviest other sub-point in the zone.
                    for _ in range(len(rseq)):
                        ds = dsubs[rseq[rcount[d] % len(rseq)]]
                        rcount[d] += 1
                        if ds.id != os.id:
                            break
                    else:
                        ds = max((s for s in dsubs if s.id != os.id), key=lambda s: s.job_w)
                alloc.append((os, ds, r_os * fv / kept_sum))

        sizes = _largest_remainder([a[2] for a in alloc], round(res_zone))
        for (os, ds, _), size in zip(alloc, sizes, strict=True):
            if size < settings.min_pop_size:  # drop tiny pops (and the points only they touch)
                continue
            secs, dist = _drive(os, ds)
            seq += 1
            pid = f"p{seq:06d}"
            pops.append(
                {
                    "id": pid,
                    "size": size,
                    "residenceId": os.id,
                    "jobId": ds.id,
                    "drivingSeconds": secs,
                    "drivingDistance": dist,
                    "drivingPath": [[os.lng, os.lat], [ds.lng, ds.lat]],
                }
            )
            residents[os.id] += size
            jobs[ds.id] += size
            point_by_id.setdefault(os.id, os)
            point_by_id.setdefault(ds.id, ds)

    points = [
        {
            "id": pid,
            "location": [sp.lng, sp.lat],
            "jobs": jobs.get(pid, 0),
            "residents": residents.get(pid, 0),
            "popIds": [],
        }
        for pid, sp in point_by_id.items()
    ]
    by_id = {p["id"]: p for p in points}
    for pop in pops:
        by_id[pop["residenceId"]]["popIds"].append(pop["id"])
        by_id[pop["jobId"]]["popIds"].append(pop["id"])

    demand = {"points": points, "pops": pops}
    geojson.write_json(demand, settings.build_dir / "demand_data.json")
    out = settings.build_dir / "demand_data.json.gz"
    geojson.write_json_gz(demand, out)
    log.info(
        "points=%d pops=%d | Σresidents=%d Σjobs=%d Σpop.size=%d -> %s (%.2f MB)",
        len(points),
        len(pops),
        sum(residents.values()),
        sum(jobs.values()),
        sum(p["size"] for p in pops),
        out.name,
        geojson.mb(out),
    )
