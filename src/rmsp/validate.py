"""Check the generated data files against the shipped-city structure."""

from __future__ import annotations

import gzip
import logging
import struct
from pathlib import Path

from rmsp import geojson
from rmsp.config import settings

log = logging.getLogger(__name__)

# depot's buildings_index.bin header: little-endian magic "SBBI" + version byte.
_BIN_MAGIC = 0x49424253
_BIN_VERSION = 1


def _load(name: str):
    return geojson.read_json_gz(settings.build_dir / name)


def validate() -> bool:
    ok = True
    checks: list[tuple[bool, str]] = []

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and cond
        checks.append((bool(cond), msg))

    # Non-demand files come from depot, so validate their game-schema essentials without
    # asserting RMSP-specific property choices (roadClass naming, exact key sets, ...).
    r = _load("roads.geojson.gz")
    check(r["type"] == "FeatureCollection" and bool(r["features"]), "roads: non-empty FC")
    check(r["features"][0]["geometry"]["type"] == "LineString", "roads: LineString")

    b = _load("buildings_index.json.gz")
    check(set(b) >= {"cs", "bbox", "grid", "cells", "buildings", "stats"}, "buildings: keys")
    check(len(b["bbox"]) == 4 and len(b["grid"]) == 2, "buildings: bbox/grid shape")
    bb = b["buildings"][0]
    check(set(bb) >= {"b", "f", "p"}, "buildings: has {b,f,p}")  # depot adds "center"
    check(b["stats"]["count"] == len(b["buildings"]), "buildings: stats.count")
    c0 = b["cells"][0]
    check(
        len(c0) >= 2 and all(0 <= i < len(b["buildings"]) for i in c0[2:]),
        "buildings: cell indices in range",
    )
    # The .bin form (required for game >1.3.0) must ship alongside the .json.
    binp: Path = settings.build_dir / "buildings_index.bin.gz"
    check(binp.exists(), "buildings.bin: present")
    if binp.exists():
        with gzip.open(binp, "rb") as f:
            head = f.read(5)
        magic, ver = struct.unpack("<IB", head)
        check(magic == _BIN_MAGIC and ver == _BIN_VERSION, "buildings.bin: header magic+version")

    o = _load("ocean_depth_index.json.gz")
    check(set(o) >= {"cs", "bbox", "grid", "cells", "depths", "stats"}, "water: keys")

    a = _load("runways_taxiways.geojson.gz")
    check(a["type"] == "FeatureCollection", "airports: FeatureCollection")
    if a["features"]:
        check(
            a["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"},
            "airports: (Multi)Polygon",
        )

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
