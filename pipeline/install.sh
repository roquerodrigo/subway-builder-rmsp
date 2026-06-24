#!/usr/bin/env bash
# Install the mod + generated data into the game.
#   - mod/index.js + mod/manifest.json  -> <game>/mods/rmsp/
#   - the 5 generated .gz data files    -> <game>/mods/rmsp/data/RMSP/  AND
#                                          <game>/cities/data/RMSP/
# Game dir comes from $SB_DATA_DIR (default: macOS Subway Builder data dir).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$HERE/.." && pwd)"
OUT="$HERE/out"

GAME_DIR="${SB_DATA_DIR:-$HOME/Library/Application Support/metro-maker4}"
MOD_DIR="$GAME_DIR/mods/rmsp"
MOD_DATA="$MOD_DIR/data/RMSP"
CITY_DATA="$GAME_DIR/cities/data/RMSP"

FILES=(roads.geojson.gz buildings_index.json.gz ocean_depth_index.json.gz \
       runways_taxiways.geojson.gz demand_data.json.gz)

echo "==> installing mod into $MOD_DIR"
mkdir -p "$MOD_DIR"
cp -f "$PROJECT/mod/index.js" "$PROJECT/mod/manifest.json" "$MOD_DIR/"

for dest in "$MOD_DATA" "$CITY_DATA"; do
  mkdir -p "$dest"
  for f in "${FILES[@]}"; do
    [ -f "$OUT/$f" ] && cp -f "$OUT/$f" "$dest/$f"
  done
  echo "installed data -> $dest"
done
echo "==> done. Enable the mod (id br.rodrigo.rmsp) in Settings > Mods and restart."
