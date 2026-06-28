"""`rmsp` — one entry point for the whole pipeline."""

from __future__ import annotations

import logging
import time
import urllib.request
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
