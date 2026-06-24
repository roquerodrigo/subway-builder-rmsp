#!/usr/bin/env bash
# Serve the RMSP vector basemap tiles for Subway Builder.
# Run this BEFORE (or while) playing so the map renders streets/buildings and
# the map://RMSP/tiles 404s stop. Leave it running in a terminal.
#   URLs: http://127.0.0.1:8080/RMSP/{z}/{x}/{y}.mvt
#         http://127.0.0.1:8080/RMSP_foundations/{z}/{x}/{y}.mvt
set -euo pipefail
TILES="$(cd "$(dirname "$0")/tiles" && pwd)"
echo "Serving $TILES on http://127.0.0.1:8080 (Ctrl+C to stop)"
exec pmtiles serve "$TILES" --port 8080 --cors "*"
