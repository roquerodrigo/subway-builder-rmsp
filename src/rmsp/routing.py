"""Real road-following commuter paths via a local OSRM server (no Docker), then
Douglas-Peucker simplification to keep demand_data light."""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rmsp import external, geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

OSRM_LOG = Path("/tmp/rmsp_osrm.log")


def _osrm_base() -> Path:
    return settings.sources_dir / "rmsp.osrm"


def _car_profile() -> Path:
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
    return (
        f"http://127.0.0.1:{settings.osrm_port}/route/v1/driving/"
        f"{o[0]},{o[1]};{d[0]},{d[1]}?overview=simplified&geometries=geojson"
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
    stats = {"ok": 0, "fail": 0}

    def work(pop: dict) -> None:
        o, d = loc.get(pop["residenceId"]), loc.get(pop["jobId"])
        if not o or not d:
            stats["fail"] += 1
            return
        try:
            with urllib.request.urlopen(_route_url(o, d), timeout=20) as r:  # noqa: S310
                data = json.load(r)
            if data.get("code") == "Ok" and data.get("routes"):
                rt = data["routes"][0]
                coords = [[round(c[0], 5), round(c[1], 5)] for c in rt["geometry"]["coordinates"]]
                if len(coords) >= 2:
                    pop["drivingPath"] = coords
                    pop["drivingSeconds"] = round(rt["duration"])
                    pop["drivingDistance"] = round(rt["distance"])
                    stats["ok"] += 1
                    return
        except Exception:
            pass
        stats["fail"] += 1

    with ThreadPoolExecutor(max_workers=settings.route_workers) as ex:
        list(ex.map(work, pops))

    geojson.write_json(demand, path)
    geojson.write_json_gz(demand, settings.build_dir / "demand_data.json.gz")
    log.info("routed ok=%d fail=%d", stats["ok"], stats["fail"])


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


def routes() -> None:
    """Full routing step: build graph, serve, route pops, simplify."""
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
    simplify_paths()
