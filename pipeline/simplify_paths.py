#!/usr/bin/env python3
"""Shrink demand_data by simplifying each pop's drivingPath with Douglas-Peucker
(keeps the road-following shape with far fewer points) and rounding coords.
Post-processes build/out/demand_data.json in place (+ .gz). No OSRM needed.

EPS_DEG ~ 0.00035 ° ≈ 38 m: arterial routes keep their shape, detail is dropped.
"""
import json, gzip, os, sys
import config

OUT = os.path.join(config.OUT, "demand_data.json")
EPS_DEG = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0015


def _perp(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    dmax, idx = 0.0, 0
    a, b = pts[0], pts[-1]
    for i in range(1, len(pts) - 1):
        d = _perp(pts[i], a, b)
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[:idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [a, b]


def main():
    with open(OUT, encoding="utf-8") as f:
        demand = json.load(f)
    before = after = 0
    for p in demand["pops"]:
        path = p.get("drivingPath")
        if not path or len(path) < 3:
            continue
        before += len(path)
        s = rdp(path, EPS_DEG)
        s = [[round(c[0], 5), round(c[1], 5)] for c in s]
        p["drivingPath"] = s
        after += len(s)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))

    n = len(demand["pops"])
    print(f"paths simplified: {before} -> {after} pts "
          f"(avg {before/n:.1f} -> {after/n:.1f} per pop)")
    print(f"  -> {OUT}.gz ({os.path.getsize(OUT + '.gz')/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
