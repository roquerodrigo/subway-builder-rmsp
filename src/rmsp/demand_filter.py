"""Prune short commutes while keeping the point/pop graph consistent.

The game pits the metro against each commuter's car trip, so commutes whose routed car
distance is under a threshold (short, local, walkable) are dropped. Removing pops also
rewrites the points that indexed them: ``popIds`` loses the dropped ids, ``residents``/
``jobs`` are recomputed from the survivors, and points left without any demand are removed.
"""

from __future__ import annotations

import json
import logging

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)


def prune_short_commutes(demand: dict, min_distance_m: float) -> dict:
    """Return *demand* with car trips shorter than *min_distance_m* removed and the points
    reindexed (popIds/residents/jobs), dropping points left without demand. Pure function."""
    kept_pops = [pop for pop in demand["pops"] if pop["drivingDistance"] >= min_distance_m]
    kept_ids = {pop["id"] for pop in kept_pops}
    referenced = {pop["residenceId"] for pop in kept_pops} | {pop["jobId"] for pop in kept_pops}

    residents: dict[str, int] = {}
    jobs: dict[str, int] = {}
    for pop in kept_pops:
        residents[pop["residenceId"]] = residents.get(pop["residenceId"], 0) + pop["size"]
        jobs[pop["jobId"]] = jobs.get(pop["jobId"], 0) + pop["size"]

    kept_points = []
    for point in demand["points"]:
        pid = point["id"]
        if pid not in referenced:
            continue
        point["popIds"] = [x for x in point["popIds"] if x in kept_ids]
        point["residents"] = residents.get(pid, 0)
        point["jobs"] = jobs.get(pid, 0)
        kept_points.append(point)

    return {"points": kept_points, "pops": kept_pops}


def drop_short_commutes(min_distance_m: float) -> None:
    """Rewrite data/build/demand_data.json(.gz) without commutes under *min_distance_m*."""
    path = settings.build_dir / "demand_data.json"
    demand = json.loads(path.read_text())
    points_before, pops_before = len(demand["points"]), len(demand["pops"])

    pruned = prune_short_commutes(demand, min_distance_m)

    geojson.write_json(pruned, path)
    out = settings.build_dir / "demand_data.json.gz"
    geojson.write_json_gz(pruned, out)
    log.info(
        "pruned %d commutes < %.0f m + %d orphan points -> %d pops, %d points (%.2f MB)",
        pops_before - len(pruned["pops"]),
        min_distance_m,
        points_before - len(pruned["points"]),
        len(pruned["pops"]),
        len(pruned["points"]),
        geojson.mb(out),
    )
