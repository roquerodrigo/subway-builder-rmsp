#!/usr/bin/env bash
# Convenience launcher: starts the RMSP tile server (if not already running)
# and opens Subway Builder. The mod auto-detects the server and enables the
# vector basemap (streets/buildings) — no more map://RMSP tile 404s.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

if ! curl -s -o /dev/null "http://127.0.0.1:8080/RMSP/12/1518/2323.mvt"; then
  echo "Starting tile server on :8080 ..."
  nohup pmtiles serve "$HERE/tiles" --port 8080 --cors "*" > /tmp/pmtiles_serve.log 2>&1 &
  sleep 2
else
  echo "Tile server already running on :8080"
fi

echo "Launching Subway Builder ..."
open -a "Subway Builder"
