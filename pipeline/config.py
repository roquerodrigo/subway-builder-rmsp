"""Shared configuration for the RMSP city build pipeline.

Paths to the *game* (where the mod + city data get installed) resolve from the
SB_DATA_DIR environment variable, defaulting to the macOS Subway Builder data
dir. Override it to install into a different copy of the game:

    SB_DATA_DIR="/path/to/Application Support/metro-maker4" python3 06_demand.py
"""
import os

CODE = "RMSP"
NAME = "São Paulo (RMSP)"

# Bounding box of the central urban mancha:
# São Paulo capital + ABC (Santo André/SBC/São Caetano/Diadema) + Guarulhos + Osasco/Barueri.
# Order: [minLng, minLat, maxLng, maxLat]
BBOX = [-46.85, -23.82, -46.36, -23.40]
MIN_LNG, MIN_LAT, MAX_LNG, MAX_LAT = BBOX

# Map center (Praça da Sé) and initial zoom.
CENTER = {"latitude": -23.5505, "longitude": -46.6333, "zoom": 11}

# Grid cell size in degrees (mirrors shipped cities ~0.0009).
CELL_SIZE = 0.0009

# --- project-local working dirs (gitignored) ---
HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(HERE, "sources")   # downloaded raw data (PBF, OD zip, OSRM graph)
OUT = os.path.join(HERE, "out")           # generated .gz data files
TILES = os.path.join(HERE, "tiles")       # generated PMTiles basemap

# --- game install targets (resolved from SB_DATA_DIR) ---
GAME_DIR = os.environ.get(
    "SB_DATA_DIR",
    os.path.expanduser("~/Library/Application Support/metro-maker4"),
)
MOD_DIR = os.path.join(GAME_DIR, "mods", "rmsp")             # where index.js/manifest.json live
MOD_DATA = os.path.join(MOD_DIR, "data", CODE)              # mod-served /data/RMSP
CITY_DATA = os.path.join(GAME_DIR, "cities", "data", CODE)  # built-in by-code convention

PBF = os.path.join(SOURCES, "sudeste-latest.osm.pbf")
PBF_CLIP = os.path.join(SOURCES, "rmsp.osm.pbf")

for d in (SOURCES, OUT, TILES):
    os.makedirs(d, exist_ok=True)


def in_bbox(lng, lat):
    return MIN_LNG <= lng <= MAX_LNG and MIN_LAT <= lat <= MAX_LAT
