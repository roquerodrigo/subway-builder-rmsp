"""Real road-following commuter paths via a local OSRM server, then Douglas-Peucker
simplification to keep demand_data light."""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rmsp import demand_filter, external, geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

OSRM_LOG = Path("/tmp/rmsp_osrm.log")


def _osrm_base() -> Path:
    return settings.sources_dir / "rmsp.osrm"


def _car_profile() -> Path:
    # the Homebrew osrm-backend keg ships the car profile under its prefix
    prefix = Path(external.capture(["brew", "--prefix", "osrm-backend"]))
    return prefix / "share" / "osrm-backend" / "profiles" / "car.lua"


def build_graph() -> None:
    """osrm-extract + partition + customize on the clipped PBF (MLD)."""
    base = _osrm_base()
    log.info("building OSRM graph")
    external.run(["osrm-extract", "-p", _car_profile(), settings.pbf_clip])
    external.run(["osrm-partition", base])
    external.run(["osrm-customize", base])


def _route_url(o: list[float], d: list[float]) -> str:
    # overview=full: ask OSRM for the full-resolution geometry and do our own
    # Douglas-Peucker (simplify_paths) so route fidelity is controlled in one place.
    return (
        f"http://127.0.0.1:{settings.osrm_port}/route/v1/driving/"
        f"{o[0]},{o[1]};{d[0]},{d[1]}?overview=full&geometries=geojson"
    )


def _wait_ready(timeout: float = 20.0) -> None:
    url = _route_url(
        [settings.center_lng, settings.center_lat],
        [settings.center_lng + 0.01, settings.center_lat + 0.01],
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2).read()  # noqa: S310
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("OSRM server did not become ready")


def route_pops() -> None:
    """Replace each pop's drivingPath/seconds/distance with the real OSRM route.
    Keeps the existing straight line on failure."""
    path = settings.build_dir / "demand_data.json"
    demand = json.loads(path.read_text())
    loc = {p["id"]: p["location"] for p in demand["points"]}
    pops = demand["pops"]
    stats = {"ok": 0, "fail": 0, "skip": 0}

    def work(pop: dict) -> None:
        o, d = loc.get(pop["residenceId"]), loc.get(pop["jobId"])
        if not o or not d or o == d:  # missing point or self-commute: keep existing values
            stats["skip"] += 1
            return
        for attempt in (1, 2):  # one retry smooths over transient OSRM/socket hiccups
            try:
                with urllib.request.urlopen(_route_url(o, d), timeout=20) as r:  # noqa: S310
                    data = json.load(r)
                if data.get("code") == "Ok" and data.get("routes"):
                    rt = data["routes"][0]
                    geom = rt["geometry"]["coordinates"]
                    coords = [[round(c[0], 5), round(c[1], 5)] for c in geom]
                    if len(coords) >= 2:
                        pop["drivingPath"] = coords
                        pop["drivingSeconds"] = round(rt["duration"])
                        pop["drivingDistance"] = round(rt["distance"])
                        stats["ok"] += 1
                        return
                break  # a valid "no route" answer: don't retry
            except Exception:
                if attempt == 2:
                    break
        stats["fail"] += 1

    with ThreadPoolExecutor(max_workers=settings.route_workers) as ex:
        list(ex.map(work, pops))

    geojson.write_json(demand, path)
    geojson.write_json_gz(demand, settings.build_dir / "demand_data.json.gz")
    log.info("routed ok=%d fail=%d skip=%d", stats["ok"], stats["fail"], stats["skip"])


def _straight_m(o: list[float], d: list[float]) -> float:
    """Straight-line distance in metres via the project's equirectangular metric
    (m_per_deg_*), consistent with how the rest of the build converts degrees<->m."""
    dx = (d[0] - o[0]) * settings.m_per_deg_lng
    dy = (d[1] - o[1]) * settings.m_per_deg_lat
    return math.hypot(dx, dy)


def straight_line_pops() -> None:
    """Toggle-simple routing: each pop's drivingPath is just the segment between its two
    points; distance from the equirectangular metric, seconds from a flat average speed.
    No OSRM server, no simplification needed (the path is already 2 points)."""
    path = settings.build_dir / "demand_data.json"
    demand = json.loads(path.read_text())
    loc = {p["id"]: p["location"] for p in demand["points"]}
    mps = settings.route_straight_speed_kmh / 3.6
    ok = skip = 0
    for pop in demand["pops"]:
        o, d = loc.get(pop["residenceId"]), loc.get(pop["jobId"])
        if not o or not d or o == d:  # missing point or self-commute
            skip += 1
            continue
        dist = _straight_m(o, d)
        pop["drivingPath"] = [[round(o[0], 5), round(o[1], 5)], [round(d[0], 5), round(d[1], 5)]]
        pop["drivingDistance"] = round(dist)
        pop["drivingSeconds"] = round(dist / mps) if mps > 0 else 0
        ok += 1
    geojson.write_json(demand, path)
    geojson.write_json_gz(demand, settings.build_dir / "demand_data.json.gz")
    log.info(
        "straight-line routed ok=%d skip=%d (@ %.0f km/h)",
        ok, skip, settings.route_straight_speed_kmh,
    )


def straighten_paths() -> None:
    """Collapse each pop's drivingPath to a straight [origin, destination] segment.
    The game renders a commute as a straight line between its two points, so the routed
    polyline's intermediate vertices are dead weight; the real OSRM drivingSeconds/
    drivingDistance are kept."""
    path = settings.build_dir / "demand_data.json"
    demand = json.loads(path.read_text())
    loc = {p["id"]: p["location"] for p in demand["points"]}
    before = after = 0
    for pop in demand["pops"]:
        o, d = loc.get(pop["residenceId"]), loc.get(pop["jobId"])
        if o is None or d is None:
            continue
        before += len(pop.get("drivingPath", []))
        pop["drivingPath"] = [[round(o[0], 5), round(o[1], 5)], [round(d[0], 5), round(d[1], 5)]]
        after += 2
    geojson.write_json(demand, path)
    out = settings.build_dir / "demand_data.json.gz"
    geojson.write_json_gz(demand, out)
    n = len(demand["pops"]) or 1
    log.info(
        "paths straightened: %d -> %d pts (avg %.1f -> %.1f) -> %s (%.2f MB)",
        before, after, before / n, after / n, out.name, geojson.mb(out),
    )


def _perp(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def rdp(pts: list[list[float]], eps: float) -> list[list[float]]:
    """Douglas-Peucker line simplification."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = _perp(pts[i], a, b)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[: idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [a, b]


def simplify_paths(eps: float | None = None) -> None:
    eps = settings.path_simplify_eps if eps is None else eps
    path = settings.build_dir / "demand_data.json"
    demand = json.loads(path.read_text())
    before = after = 0
    for p in demand["pops"]:
        coords = p.get("drivingPath")
        if not coords or len(coords) < 3:
            continue
        before += len(coords)
        s = [[round(c[0], 5), round(c[1], 5)] for c in rdp(coords, eps)]
        p["drivingPath"] = s
        after += len(s)
    geojson.write_json(demand, path)
    out = settings.build_dir / "demand_data.json.gz"
    geojson.write_json_gz(demand, out)
    n = len(demand["pops"]) or 1
    log.info(
        "paths simplified: %d -> %d pts (avg %.1f -> %.1f) -> %s (%.2f MB)",
        before,
        after,
        before / n,
        after / n,
        out.name,
        geojson.mb(out),
    )


def _prune_short_commutes() -> None:
    if settings.min_driving_distance_m > 0:
        demand_filter.drop_short_commutes(settings.min_driving_distance_m)


def routes() -> None:
    """Full routing step: build the OSRM graph, route each commute on the road network,
    drop the short ones (min_driving_distance_m), then lay down the final trip geometry —
    a straight origin->destination segment (straight_path_geometry, the game's own rendering)
    or the Douglas-Peucker road line. With RMSP_ROUTE_STRAIGHT_LINE set, connect each pop's
    points directly without OSRM."""
    if settings.route_straight_line:
        log.info("straight-line routing (RMSP_ROUTE_STRAIGHT_LINE)")
        straight_line_pops()
        _prune_short_commutes()
        return
    build_graph()
    proc = external.popen(
        ["osrm-routed", "--algorithm", "mld", _osrm_base(), "-p", str(settings.osrm_port)],
        OSRM_LOG,
    )
    try:
        _wait_ready()
        route_pops()
    finally:
        proc.terminate()
    _prune_short_commutes()
    if settings.straight_path_geometry:
        straighten_paths()
    else:
        simplify_paths()
