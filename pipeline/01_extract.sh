#!/usr/bin/env bash
# Extract feature subsets from the clipped RMSP PBF into GeoJSONSeq files.
# Fast C++ osmium passes; Python formatters consume the .geojsonseq outputs.
set -euo pipefail
cd "$(dirname "$0")/sources"

PBF="rmsp.osm.pbf"

echo "==> roads (lines)"
osmium tags-filter -o _roads.pbf --overwrite "$PBF" \
  w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,residential,living_street,unclassified,road
osmium export _roads.pbf -o roads.geojsonseq -f geojsonseq --geometry-types=linestring \
  -a type --overwrite

echo "==> buildings (polygons)"
osmium tags-filter -o _bldg.pbf --overwrite "$PBF" a/building
osmium export _bldg.pbf -o buildings.geojsonseq -f geojsonseq --geometry-types=polygon \
  --overwrite

echo "==> water (polygons)"
osmium tags-filter -o _water.pbf --overwrite "$PBF" \
  a/natural=water a/landuse=reservoir a/water
osmium export _water.pbf -o water.geojsonseq -f geojsonseq --geometry-types=polygon \
  --overwrite

echo "==> airports (aeroway polygons + lines)"
osmium tags-filter -o _aero.pbf --overwrite "$PBF" \
  nwr/aeroway=runway,taxiway,apron,aerodrome
osmium export _aero.pbf -o aero.geojsonseq -f geojsonseq \
  --geometry-types=polygon,linestring --overwrite

echo "==> done"
wc -l roads.geojsonseq buildings.geojsonseq water.geojsonseq aero.geojsonseq
