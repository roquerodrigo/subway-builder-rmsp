"""Check the generated data files against the shipped-city structure."""

from __future__ import annotations

import logging

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)


def _load(name: str):
    return geojson.read_json_gz(settings.build_dir / name)


def validate() -> bool:
    ok = True
    checks: list[tuple[bool, str]] = []

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and cond
        checks.append((bool(cond), msg))

    r = _load("roads.geojson.gz")
    check(r["type"] == "FeatureCollection", "roads: FeatureCollection")
    f0 = r["features"][0]
    check(f0["geometry"]["type"] == "LineString", "roads: LineString")
    check(set(f0["properties"]) == {"roadClass", "structure", "name"}, "roads: props")
    classes = {ft["properties"]["roadClass"] for ft in r["features"]}
    check(classes <= {"highway", "major", "minor"}, f"roads: classes {classes}")

    b = _load("buildings_index.json.gz")
    check(set(b) >= {"cs", "bbox", "grid", "cells", "buildings", "stats"}, "buildings: keys")
    check(len(b["bbox"]) == 4 and len(b["grid"]) == 2, "buildings: bbox/grid shape")
    bb = b["buildings"][0]
    check(set(bb) == {"b", "f", "p"}, "buildings: {b,f,p}")
    check(isinstance(bb["f"], int) and bb["f"] >= 1, "buildings: f positive int")
    check(b["stats"]["count"] == len(b["buildings"]), "buildings: stats.count")
    c0 = b["cells"][0]
    check(
        len(c0) >= 2 and all(0 <= i < len(b["buildings"]) for i in c0[2:]),
        "buildings: cell indices in range",
    )

    o = _load("ocean_depth_index.json.gz")
    check(set(o) >= {"cs", "bbox", "grid", "cells", "depths", "stats"}, "water: keys")
    if o["depths"]:
        d0 = o["depths"][0]
        check(set(d0) == {"b", "d", "p"}, "water: {b,d,p}")
        check(d0["d"] < 0, "water: depth negative")

    a = _load("runways_taxiways.geojson.gz")
    check(a["type"] == "FeatureCollection", "airports: FeatureCollection")
    if a["features"]:
        check(a["features"][0]["geometry"]["type"] == "MultiPolygon", "airports: MultiPolygon")

    d = _load("demand_data.json.gz")
    check(set(d) == {"points", "pops"}, "demand: {points,pops}")
    check(
        set(d["points"][0]) == {"id", "location", "jobs", "residents", "popIds"},
        "demand: point keys",
    )
    pop0 = d["pops"][0]
    req = {"id", "size", "residenceId", "jobId", "drivingSeconds", "drivingDistance"}
    check(req <= set(pop0) <= req | {"drivingPath"}, "demand: pop keys")
    ids = {p["id"] for p in d["points"]}
    bad = [pp for pp in d["pops"] if pp["residenceId"] not in ids or pp["jobId"] not in ids]
    check(not bad, f"demand: pop ids resolve ({len(bad)} bad)")
    allpop = {pp["id"] for pp in d["pops"]}
    linked = {pid for p in d["points"] for pid in p["popIds"]}
    check(linked <= allpop, "demand: point.popIds reference real pops")

    for passed, msg in checks:
        log.info("  %s  %s", "OK " if passed else "FAIL", msg)
    log.info("%s", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return ok
