# subway-builder-rmsp

Generator that builds a playable São Paulo metro area (RMSP) city for
[Subway Builder](https://www.subwaybuilder.com), packaged as a Railyard map
bundle (local import). Non-demand files (roads, buildings index, airports,
ocean depth, PMTiles basemap) come from the official `depot` library; the
demand is downloaded pre-built from the `subway-builder-rmsp-demand-data`
release and only routed here. Public repo: `roquerodrigo/subway-builder-rmsp`.

## Setup

`depot` shells out to many CLI tools (osmium, tippecanoe/tile-join, pmtiles,
osrm-*, ogr2ogr, jq, sqlite3, java, node, mapshaper, planetiler.jar) and its
`MapGen` constructor fails if any is missing — the full install list is in the
README's **Pré-requisitos** section. Then `uv sync`.

Knobs are env-overridable: copy `.env.example` to `.env` (a shell `export`
still wins over `.env`). Only scalar knobs are; bbox and the special-demand
POIs live in code.

## Running

```bash
uv run rmsp all         # sources -> generate -> demand -> [specials] -> routes -> validate
uv run rmsp bundle --version X.Y.Z --repo https://github.com/roquerodrigo/subway-builder-rmsp
```

Steps of `all`, individually: `sources`, `generate`, `demand`, `specials`
(only runs inside `all` when `RMSP_SPECIAL_DEMAND=1`), `routes`, `validate`.
`specials` must run before `routes` so the injected pops get routed.
`rmsp debug` relaunches the macOS game with `DEBUG_PROD=true` and logs the
console to `logs/`.

In-game: Railyard → **Library → Import Asset** → the bundle `.zip`; then
**Select city → 🇧🇷 Brazil tab → São Paulo**.

## Test & lint

```bash
uv run pytest           # tests/test_pure.py — pure/deterministic helpers only
uv run ruff check .
```

No test/lint CI workflow (the only workflow is auto-assign) — run pytest/ruff
locally before pushing.

## Conventions and gotchas

- **`config.py` is the single source of truth.** Every magic number (bbox,
  simplification tolerances, ports, URLs, paths) lives in `Settings`, not
  scattered across modules.
- **Demand comes from another repo.** `RMSP_DEMAND_URL` pins a
  `subway-builder-rmsp-demand-data` release asset (`demand_data.json.gz`);
  a schema change there breaks `validate.py`'s exact key checks.
- **OD demand invariant**: `points.residents`/`points.jobs` are the
  commute-matrix marginals (Σ `pop.size` by home / by workplace zone), **not**
  the zone's total population — the game requires
  `Σ residents == Σ jobs == Σ pop.size`. Each pop is listed in the `popIds` of
  **both** its origin and destination zones, otherwise the Workers tab shows
  no arrival/departure times. Anything that drops pops (e.g.
  `demand_filter.prune_short_commutes`) must rebuild `popIds`/`residents`/`jobs`
  and drop demand-less points.
- **`routes`** routes every pop on OSRM (real `drivingSeconds`/`drivingDistance`),
  drops car trips under `RMSP_MIN_DRIVING_DISTANCE_M`, then by default collapses
  `drivingPath` to a straight origin→destination segment (the game draws it
  straight anyway). The OSRM car profile is located via
  `brew --prefix osrm-backend`, so routing assumes a Homebrew osrm-backend.
- **Buildings pre-filter**: `generate.py` drops Overture buildings under
  `RMSP_BLDG_PREFILTER_M2` before depot's mapshaper step, which otherwise OOMs on
  the whole metro. Keep it below `RMSP_BLDG_AREA_MIN_M2` so depot's own filter
  still makes the final cut. It drives depot through its private
  `_fetch_overture_buildings` / `buildings_geojson` — recheck on any depot bump
  (pinned by git tag in `pyproject.toml`).
- **Buildings**: the `buildings_index` field `f` is the **foundation depth**
  (basement levels, default 1) the game reads as `foundationDepth` when
  tunnelling under buildings — it is unrelated to above-ground floor count.
  Both `buildings_index.json.gz` and `.bin.gz` ship (game ≤1.3.0 reads the JSON,
  newer reads the bin).
- **`rmsp bundle`** packages the Railyard distribution ZIP (flat, no
  subfolders) at `dist/<CODE>-<version>.zip`, plus the Update JSON
  `dist/<CODE>.json`: `config.json` + the game data `.gz` files +
  `<CODE>.pmtiles`. The registry's integrity check accepts the data files
  gzipped, so the pipeline's existing `.gz` output is reused as-is — no
  re-encoding step. The download link assumes the GitHub Release tag is
  `v<version>`. `population` defaults to the simulated Σ `pop.size` of the
  built demand (override with `RMSP_POPULATION`).
- User-facing strings (README, `config.json` description, changelog) are in
  Portuguese since the source data and primary audience are Brazilian; code
  identifiers and this file are in English (comments/docstrings are mixed —
  `specials.py` is in Portuguese).
