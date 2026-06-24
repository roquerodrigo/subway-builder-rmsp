#!/usr/bin/env python3
"""Validate generated RMSP data files against the shipped-city structure."""
import json, gzip, os, sys
import config

OUT = config.OUT


def load(name):
    with gzip.open(os.path.join(OUT, name), "rt", encoding="utf-8") as f:
        return json.load(f)


def check(cond, msg):
    print(("  OK  " if cond else " FAIL ") + msg)
    return cond


def main():
    ok = True

    print("roads.geojson.gz")
    r = load("roads.geojson.gz")
    ok &= check(r["type"] == "FeatureCollection", "FeatureCollection")
    f0 = r["features"][0]
    ok &= check(f0["geometry"]["type"] == "LineString", "LineString geom")
    ok &= check(set(f0["properties"]) == {"roadClass", "structure", "name"},
                "props {roadClass,structure,name}")
    classes = {ft["properties"]["roadClass"] for ft in r["features"]}
    ok &= check(classes <= {"highway", "major", "minor"}, f"roadClass values {classes}")

    print("buildings_index.json.gz")
    b = load("buildings_index.json.gz")
    ok &= check(set(b) >= {"cs", "bbox", "grid", "cells", "buildings", "stats"},
                "keys")
    ok &= check(len(b["bbox"]) == 4 and len(b["grid"]) == 2, "bbox/grid shape")
    bb = b["buildings"][0]
    ok &= check(set(bb) == {"b", "f", "p"}, "building {b,f,p}")
    ok &= check(isinstance(bb["f"], int) and bb["f"] >= 1, "f is positive int")
    ok &= check(b["stats"]["count"] == len(b["buildings"]), "stats.count matches")
    c0 = b["cells"][0]
    ok &= check(len(c0) >= 2 and all(0 <= i < len(b["buildings"]) for i in c0[2:]),
                "cell indices in range")

    print("ocean_depth_index.json.gz")
    o = load("ocean_depth_index.json.gz")
    ok &= check(set(o) >= {"cs", "bbox", "grid", "cells", "depths", "stats"}, "keys")
    if o["depths"]:
        d0 = o["depths"][0]
        ok &= check(set(d0) == {"b", "d", "p"}, "depth {b,d,p}")
        ok &= check(d0["d"] < 0, "depth negative")

    print("runways_taxiways.geojson.gz")
    a = load("runways_taxiways.geojson.gz")
    ok &= check(a["type"] == "FeatureCollection", "FeatureCollection")
    if a["features"]:
        ok &= check(a["features"][0]["geometry"]["type"] == "MultiPolygon",
                    "MultiPolygon geom")

    print("demand_data.json.gz")
    d = load("demand_data.json.gz")
    ok &= check(set(d) == {"points", "pops"}, "{points,pops}")
    p0 = d["points"][0]
    ok &= check(set(p0) == {"id", "location", "jobs", "residents", "popIds"},
                "point keys")
    pop0 = d["pops"][0]
    required_pop = {"id", "size", "residenceId", "jobId",
                    "drivingSeconds", "drivingDistance"}
    ok &= check(required_pop <= set(pop0) <= required_pop | {"drivingPath"},
                "pop keys (+ optional drivingPath)")
    if "drivingPath" in pop0:
        ok &= check(len(pop0["drivingPath"]) >= 2, "drivingPath has >=2 points")
    ids = {p["id"] for p in d["points"]}
    bad = [pp for pp in d["pops"]
           if pp["residenceId"] not in ids or pp["jobId"] not in ids]
    ok &= check(not bad, f"all pop residence/job ids resolve ({len(bad)} bad)")
    allpop = {pp["id"] for pp in d["pops"]}
    linked = {pid for p in d["points"] for pid in p["popIds"]}
    ok &= check(linked <= allpop, "point.popIds reference real pops")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
