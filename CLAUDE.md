# subway-builder-rmsp

Generator + mod that builds a playable São Paulo metro area (RMSP) city for
[Subway Builder](https://www.subwaybuilder.com) (modding API v1.0.0). It turns
OpenStreetMap extracts and the Metrô-SP Origin-Destination survey into the
game's native data files, a vector basemap, and a mod that installs both into
the game's data directory. Public repo: `roquerodrigo/subway-builder-rmsp`.

## Setup

```bash
brew install osmium-tool tippecanoe pmtiles osrm-backend uv
uv sync                # creates .venv, installs the package + deps
```

Game data directory resolves from `SB_DATA_DIR` (default: the macOS Subway
Builder path, `~/Library/Application Support/metro-maker4`).

## Running

Full pipeline (download sources, build everything, validate, install into the game):

```bash
uv run rmsp all
```

Or step by step:

```bash
uv run rmsp sources     # Geofabrik southeast extract + Pesquisa OD; clip to bbox; extract OSM subsets
uv run rmsp build        # 5 game data files -> data/build/  (--only roads,buildings,water,airports,demand)
uv run rmsp routes       # real road-following commuter paths (OSRM, no Docker)
uv run rmsp tiles        # vector basemap (PMTiles)
uv run rmsp validate     # check the .gz files against the shipped-city schema
uv run rmsp install      # copy mod + data into the game (SB_DATA_DIR)
```

Play (basemap needs the local tile server — a mod sandbox limitation):

```bash
uv run rmsp play        # starts pmtiles serve :8080 if needed, opens the game
# or: uv run rmsp serve  (blocking, in its own terminal) + open the game manually
```

In-game: **Settings → Mods** → enable **RMSP**; then **Select city → 🇧🇷 Brazil
tab → São Paulo (RMSP)**.

Publish a new release to the Railyard registry: see `PUBLISHING.md` for the
full flow (`rmsp bundle` → GitHub Release → registry issue).

## Test & lint

```bash
uv run pytest           # tests/test_pure.py — pure/deterministic helpers only
uv run ruff check .     # lint (E, F, I, UP, B), line-length 100
```

No CI workflow configured — run pytest/ruff locally before pushing.

## Conventions and gotchas

- **`config.py` is the single source of truth.** Every magic number (bbox,
  simplification tolerances, motive codes, ports, URLs, paths) lives in
  `Settings`, not scattered across modules.
- **OD demand invariant**: `points.residents`/`points.jobs` are the
  commute-matrix marginals (Σ `pop.size` by home / by workplace zone), **not**
  the zone's total population — the game requires
  `Σ residents == Σ jobs == Σ pop.size`. Each pop is listed in the `popIds` of
  **both** its origin and destination zones, otherwise the Workers tab shows
  no arrival/departure times.
- **`drivingPath`** starts as a straight line in `demand.py` and is only
  replaced with a real road route by `routing.py` (needs a local OSRM server,
  no Docker required).
- **Basemap layers** must match what the game's style renders: `water`,
  `parks`, `buildings`, `airports`, plus `city_labels`/`suburb_labels`/
  `neighborhood_labels` and `foundations`/`ocean_foundations`. Each feature
  only carries the property its layer reads: `parks → area`,
  `buildings → height` (m), `foundations → foundationDepth`,
  `water`/`ocean_foundations → depth_min`, labels → `name`. `mod/index.js`
  sets `oceanFoundations:false` — without it the `water` layer stays
  `visibility:none`.
- **Buildings**: 3D height comes from the tile's `buildings.height` (derived
  from OSM `height`/`building:levels`). The `buildings_index` field `f` is the
  **foundation depth** (basement levels, default 1) the game reads as
  `foundationDepth` when tunnelling under buildings — it is unrelated to
  above-ground floor count.
- **`SubwayBuilderAPI` version is 1.0.0**, confirmed at runtime even though the
  game app itself reports 1.3.0 — don't assume they track together.
- **Known non-fatal console error**: `layers[N]: source "general-tiles" not
  found`, triggered by the custom basemap's `setTileURLOverride`. Transitory,
  the map renders fine; there is no clean fix from the mod side since the
  game rebuilds its style internally and MapLibre isn't reachable from mod
  code.
- **`rmsp bundle`** packages the Railyard distribution ZIP (flat, no
  subfolders): `config.json` + the game data `.gz` files + `<CODE>.pmtiles`.
  The registry's integrity check accepts the data files gzipped, so the
  pipeline's existing `.gz` output is reused as-is — no re-encoding step.
  `config.json`'s `version` must match the GitHub Release tag.
- User-facing strings (README, mod description, OD survey field meanings) are
  in Portuguese since the source data and primary audience are Brazilian;
  code, comments, and this file are in English.
