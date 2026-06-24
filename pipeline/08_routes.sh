#!/usr/bin/env bash
# Build an OSRM car graph from the RMSP OSM extract, serve it, and rewrite every
# pop's drivingPath with the real road route (route_paths.py). No Docker needed.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/sources"
PROFILE="$(brew --prefix osrm-backend)/share/osrm-backend/profiles/car.lua"
PBF="rmsp.osm.pbf"
BASE="rmsp.osrm"

echo "==> osrm-extract ($PROFILE)"
osrm-extract -p "$PROFILE" "$PBF"
echo "==> osrm-partition"
osrm-partition "$BASE"
echo "==> osrm-customize"
osrm-customize "$BASE"

echo "==> starting osrm-routed (mld) on :5050 (5000 is macOS AirPlay)"
osrm-routed --algorithm mld "$BASE" -p 5050 > /tmp/osrm_routed.log 2>&1 &
OSRM_PID=$!
sleep 5

echo "==> routing pops -> road geometry"
python3 "$HERE/route_paths.py"

echo "==> stopping osrm-routed"
kill "$OSRM_PID" 2>/dev/null || true

echo "==> simplifying paths (Douglas-Peucker) to keep the file light"
python3 "$HERE/simplify_paths.py" 0.002
echo "==> done"
