"""`rmsp` — one entry point for the whole pipeline."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import typer

from rmsp import demand, generate, publish, routing, sources, specials, validate
from rmsp.config import settings

app = typer.Typer(
    add_completion=False,
    help="Generate the RMSP city for Subway Builder (Railyard map bundle).",
)

_state = {"verbose": False}


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="debug logging")) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")
    _state["verbose"] = verbose


@app.command(name="sources")
def cmd_sources() -> None:
    """Download the Geofabrik PBF and clip it to the city bbox (basemap + routing source)."""
    sources.acquire()


@app.command(name="generate")
def cmd_generate() -> None:
    """Generate the non-demand files via depot (roads, buildings json+bin, airports,
    ocean_depth, PMTiles) into data/build + data/tiles."""
    generate.generate_base(verbose=_state["verbose"])


@app.command(name="demand")
def cmd_demand() -> None:
    """Download the pre-built demand (subway-builder-rmsp-demand-data release) into data/build/."""
    demand.fetch()


@app.command(name="specials")
def cmd_specials() -> None:
    """Inject special demand POIs (airport, park, stadium, …) into data/build/demand_data.json.

    Run after the base demand is in data/build and before `routes` so the new pops get routed."""
    specials.add_specials()


@app.command()
def routes() -> None:
    """Build the OSRM graph, route each commute on the road network, drop the short trips
    (RMSP_MIN_DRIVING_DISTANCE_M) and lay down the final straight-line trip geometry."""
    routing.routes()


@app.command(name="validate")
def cmd_validate() -> None:
    """Check the generated data files against the game's schema."""
    if not validate.validate():
        raise typer.Exit(1)


@app.command()
def bundle(
    version: str = typer.Option("1.0.0", help="release version (config.json + Update JSON)"),
    repo: str = typer.Option(
        "", help="GitHub repo URL for the download link, e.g. https://github.com/<owner>/<repo>"
    ),
    changelog: str = typer.Option("Primeira versão.", help="changelog for this version"),
) -> None:
    """Package the Railyard map bundle (dist/<CODE>.zip + Update JSON)."""
    publish.bundle(version=version, repo=repo or None, changelog=changelog)


@app.command(name="all")
def cmd_all() -> None:
    """Full pipeline: sources -> generate -> demand -> [specials] -> routes -> validate.

    Demand is downloaded from the demand-data release (`demand`), not built here. Special
    demand POIs are opt-in (RMSP_SPECIAL_DEMAND). `routes` also drops short commutes and
    straightens the trip geometry (see its config knobs). Produces the validated data in
    data/build + data/tiles; run `rmsp bundle` to package the Railyard map .zip you then
    import locally into Railyard."""
    sources.acquire()
    generate.generate_base(verbose=_state["verbose"])
    demand.fetch()
    if settings.special_demand:
        specials.add_specials()
    routing.routes()
    if not validate.validate():
        raise typer.Exit(1)


@app.command()
def debug(
    app_path: str = typer.Option(
        "/Applications/Subway Builder.app", "--app", help="Subway Builder .app bundle"
    ),
) -> None:
    """Relaunch the game with DEBUG_PROD=true so the prod build opens its DevTools/console,
    capturing the console to a timestamped log in logs/. The env var only applies on a fresh
    launch and macOS `open` drops it, so the running game is quit and its binary started
    directly. Import the map via Railyard first — the game serves the tiles, no local server."""
    logs = settings.logs_dir
    logs.mkdir(parents=True, exist_ok=True)
    name = Path(app_path).stem  # "Subway Builder"
    exe = Path(app_path) / "Contents" / "MacOS" / name
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
    typer.echo(f"debug: {name} (DEBUG_PROD) -> log {log_path}")
