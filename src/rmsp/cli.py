"""`rmsp` — one entry point for the whole pipeline."""

from __future__ import annotations

import logging
import os
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import typer

from rmsp import demand, external, install, layers, publish, routing, sources, tiles, validate
from rmsp.config import settings

app = typer.Typer(add_completion=False, help="Generate & install the RMSP city for Subway Builder.")

_BUILD_STEPS = {
    "roads": layers.build_roads,
    "buildings": layers.build_buildings,
    "water": layers.build_water,
    "airports": layers.build_airports,
    "demand": demand.build_demand,
}


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="debug logging")) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")


@app.command(name="sources")
def cmd_sources() -> None:
    """Download the OSM extract + OD survey, clip to bbox, extract OSM subsets."""
    sources.acquire()


@app.command()
def build(
    only: str = typer.Option("all", help="comma list: roads,buildings,water,airports,demand"),
) -> None:
    """Generate the 5 game data files into data/build/."""
    settings.ensure_dirs()
    names = list(_BUILD_STEPS) if only == "all" else [s.strip() for s in only.split(",")]
    for name in names:
        _BUILD_STEPS[name]()


@app.command(name="cnefe")
def cmd_cnefe() -> None:
    """Build the CNEFE proxy: address points + Censo setor population (demand_proxy=cnefe)."""
    settings.ensure_dirs()
    if settings.demand_proxy != "cnefe":
        typer.echo("set RMSP_DEMAND_PROXY=cnefe to build the CNEFE proxy")
        raise typer.Exit(1)
    sources.cnefe()
    sources.censo()


@app.command()
def routes() -> None:
    """Build the OSRM graph and replace pop drivingPaths with real road routes."""
    routing.routes()


@app.command(name="tiles")
def cmd_tiles() -> None:
    """Build the PMTiles vector basemap (basemap + foundations)."""
    tiles.build_tiles()


@app.command(name="validate")
def cmd_validate() -> None:
    """Check the generated data files against the game's schema."""
    if not validate.validate():
        raise typer.Exit(1)


@app.command(name="install")
def cmd_install() -> None:
    """Copy the mod + data into the game (SB_DATA_DIR)."""
    install.install()


@app.command()
def serve() -> None:
    """Serve the tiles on http://127.0.0.1:8080 (blocking)."""
    tiles.serve_tiles()


@app.command()
def play() -> None:
    """Start the tile server (if needed) in the background and open the game."""
    probe = f"http://127.0.0.1:{settings.tile_server_port}/RMSP/12/1518/2323.mvt"
    try:
        urllib.request.urlopen(probe, timeout=1).read()  # noqa: S310
    except Exception:
        external.popen(
            [
                "pmtiles",
                "serve",
                settings.tiles_dir,
                "--port",
                str(settings.tile_server_port),
                "--cors",
                "*",
            ],
            Path("/tmp/rmsp_tiles.log"),
        )
        time.sleep(2)
    external.run(["open", "-a", "Subway Builder"])


@app.command()
def debug(
    app: str = typer.Option("/Applications/Subway Builder.app", help="Subway Builder .app bundle"),
) -> None:
    """Dev mode: restart the tile server fresh (so a just-rebuilt RMSP.pmtiles is served,
    not a cached one) and relaunch the game with DEBUG_PROD=true, which makes the prod
    build open its DevTools/console. The env var only applies on a fresh launch and macOS
    `open` drops it, so the running game is quit and its binary started directly."""
    settings.ensure_dirs()
    logs = settings.logs_dir
    logs.mkdir(parents=True, exist_ok=True)
    # 1. always restart the tile server so the freshest tiles are served
    subprocess.run(["pkill", "-f", "pmtiles serve"], check=False)
    time.sleep(1)
    port = str(settings.tile_server_port)
    external.popen(
        ["pmtiles", "serve", settings.tiles_dir, "--port", port, "--cors", "*"],
        logs / "tiles.log",
    )
    time.sleep(2)
    # 2. relaunch the game with DEBUG_PROD set, its console captured to a timestamped log
    name = Path(app).stem  # "Subway Builder"
    exe = Path(app) / "Contents" / "MacOS" / name
    if not exe.exists():
        typer.echo(f"game binary not found: {exe} (pass --app)")
        raise typer.Exit(1)
    subprocess.run(["osascript", "-e", f'quit app "{name}"'], check=False)
    time.sleep(1)
    log_path = logs / f"debug-{datetime.now():%Y%m%d-%H%M%S}.log"
    fh = open(log_path, "w")  # noqa: SIM115 — inherited by the game; closing would kill its log
    subprocess.Popen(
        [str(exe)],
        env={**os.environ, "DEBUG_PROD": "true"},
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    typer.echo(f"debug: tiles re-served + {name} (DEBUG_PROD) -> log {log_path}")


@app.command()
def bundle(
    version: str = typer.Option("1.0.0", help="release version (config.json + Update JSON)"),
    repo: str = typer.Option(
        "", help="GitHub repo URL for the download link, e.g. https://github.com/<owner>/<repo>"
    ),
    changelog: str = typer.Option("Primeira versão.", help="changelog for this version"),
) -> None:
    """Package the Railyard map bundle (data/dist/<CODE>.zip + Update JSON)."""
    publish.bundle(version=version, repo=repo or None, changelog=changelog)


@app.command(name="all")
def cmd_all() -> None:
    """Full pipeline: sources -> build -> routes -> tiles -> validate -> install."""
    sources.acquire()
    layers.build_all()
    demand.build_demand()
    routing.routes()
    tiles.build_tiles()
    if not validate.validate():
        raise typer.Exit(1)
    install.install()
