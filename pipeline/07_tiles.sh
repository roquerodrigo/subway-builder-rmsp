#!/usr/bin/env bash
# Build the vector basemap (PMTiles) so the game stops 404-ing on
# map://RMSP/tiles/* and map://RMSP/foundations/* and actually renders water,
# parks, buildings and airports. Layer names must match the game's style:
#   basemap:     water, parks, buildings, airports
#   foundations: foundations (building footprints), ocean_foundations (water)
set -euo pipefail
cd "$(dirname "$0")/sources"
PBF=rmsp.osm.pbf
TILES="../tiles"; mkdir -p "$TILES"

echo "==> extracting parks/green areas"
osmium tags-filter -o _parks.pbf --overwrite "$PBF" \
  a/leisure=park,nature_reserve,garden a/landuse=forest,grass,recreation_ground,meadow,village_green a/natural=wood
osmium export _parks.pbf -o parks.geojsonseq -f geojsonseq --geometry-types=polygon --overwrite

echo "==> stripping RS (0x1e) -> plain NDJSON for tippecanoe"
for f in water buildings aero parks; do tr -d '\036' < "$f.geojsonseq" > "$f.ndjson"; done

echo "==> basemap tiles -> RMSP.pmtiles"
tippecanoe -o "$TILES/RMSP.pmtiles" --force -Z8 -z15 \
  -L water:water.ndjson \
  -L parks:parks.ndjson \
  -L airports:aero.ndjson \
  -L buildings:buildings.ndjson \
  --drop-densest-as-needed --coalesce-densest-as-needed \
  --extend-zooms-if-still-dropping --no-tile-size-limit

echo "==> foundation tiles -> RMSP_foundations.pmtiles"
tippecanoe -o "$TILES/RMSP_foundations.pmtiles" --force -Z12 -z15 \
  -L foundations:buildings.ndjson \
  -L ocean_foundations:water.ndjson \
  --drop-densest-as-needed --no-tile-size-limit

echo "==> done"
ls -la "$TILES"
