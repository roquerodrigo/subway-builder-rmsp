#!/usr/bin/env python3
"""Replace each pop's straight-line drivingPath with a real road route from a
local OSRM server (http://127.0.0.1:5000), and update drivingSeconds/
drivingDistance with OSRM's values. Falls back to the existing straight line
when a route can't be found.

Run AFTER 06_demand.py and with osrm-routed serving (see 08_routes.sh).
"""
import json, gzip, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import config

OSRM = "http://127.0.0.1:5050"  # 5000 is taken by macOS Control Center (AirPlay)
OUT = os.path.join(config.OUT, "demand_data.json")
WORKERS = 8


def route(o, d):
    url = (f"{OSRM}/route/v1/driving/{o[0]},{o[1]};{d[0]},{d[1]}"
           "?overview=simplified&geometries=geojson")
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    rt = data["routes"][0]
    coords = [[round(c[0], 5), round(c[1], 5)] for c in rt["geometry"]["coordinates"]]
    return rt["duration"], rt["distance"], coords


def main():
    with open(OUT, encoding="utf-8") as f:
        demand = json.load(f)
    loc = {p["id"]: p["location"] for p in demand["points"]}
    pops = demand["pops"]

    done = {"ok": 0, "fail": 0}

    def work(pop):
        o = loc.get(pop["residenceId"]); d = loc.get(pop["jobId"])
        if not o or not d:
            done["fail"] += 1
            return
        try:
            res = route(o, d)
            if res:
                secs, dist, coords = res
                if len(coords) >= 2:
                    pop["drivingPath"] = coords
                    pop["drivingSeconds"] = int(round(secs))
                    pop["drivingDistance"] = int(round(dist))
                    done["ok"] += 1
                    return
        except Exception:
            pass
        done["fail"] += 1  # keep existing straight-line drivingPath

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, _ in enumerate(ex.map(work, pops), 1):
            if i % 1000 == 0:
                print(f"  routed {i}/{len(pops)} (ok={done['ok']} fail={done['fail']})")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))

    npts = sum(len(p.get("drivingPath", [])) for p in pops)
    print(f"routed ok={done['ok']} fail(kept straight)={done['fail']} "
          f"avg pts/path={npts/len(pops):.1f}")
    print(f"  -> {OUT}.gz ({os.path.getsize(OUT + '.gz')/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
