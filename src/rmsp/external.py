"""Thin wrappers around the external binaries the pipeline shells out to
(osmium, tippecanoe, osrm-*, pmtiles).

On Linux these run in Docker containers instead of Homebrew binaries: the
project root is bind-mounted so the absolute ``data/`` paths resolve identically
inside the container, files are written back as the host user, and the
long-running servers (osrm-routed, pmtiles serve) publish their port on
127.0.0.1. One place to check availability, log the command and surface errors.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from rmsp.config import PROJECT_ROOT, settings

log = logging.getLogger(__name__)


def _docker_tools() -> dict[str, tuple[str, str]]:
    """tool name -> (image, in-container binary). Image resolved from settings."""
    return {
        "osmium": (settings.tools_image, "osmium"),
        "tippecanoe": (settings.tools_image, "tippecanoe"),
        "tile-join": (settings.tools_image, "tile-join"),
        "osrm-extract": (settings.osrm_image, "osrm-extract"),
        "osrm-partition": (settings.osrm_image, "osrm-partition"),
        "osrm-customize": (settings.osrm_image, "osrm-customize"),
        "osrm-routed": (settings.osrm_image, "osrm-routed"),
        "pmtiles": (settings.pmtiles_image, "/go-pmtiles"),
    }


# servers started via popen() need their container port published on the host
_SERVER_PORTS: dict[str, int] = {
    "osrm-routed": settings.osrm_port,
    "pmtiles": settings.tile_server_port,
}


def _is_docker_tool(tool: str) -> bool:
    return settings.use_docker and tool in _docker_tools()


def _docker_cmd(args: list[str], *, server: bool = False) -> list[str]:
    """Wrap ``args`` (argv[0] is the tool) into a ``docker run`` invocation."""
    tool = args[0]
    image, binary = _docker_tools()[tool]
    cmd = ["docker", "run", "--rm"]
    if server:
        port = _SERVER_PORTS[tool]
        cmd += ["--name", f"sbrmsp-{tool}", "-p", f"127.0.0.1:{port}:{port}"]
    # write generated files back as the host user, not root
    cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    # mount the project so absolute data/ paths resolve identically in-container
    cmd += ["-v", f"{PROJECT_ROOT}:{PROJECT_ROOT}", "-w", str(PROJECT_ROOT)]
    cmd += ["--entrypoint", binary, image]
    cmd += [str(a) for a in args[1:]]
    return cmd


def require(*binaries: str) -> None:
    """Raise a clear error if a needed binary (or Docker) is missing."""
    needed = {("docker" if _is_docker_tool(b) else b) for b in binaries}
    missing = [b for b in needed if shutil.which(b) is None]
    if missing:
        hint = (
            "install Docker"
            if "docker" in missing
            else f"install {', '.join(missing)} (or set use_docker=False)"
        )
        raise RuntimeError(f"missing tool(s): {', '.join(missing)} — {hint}")


def run(cmd: list[str | Path], **kwargs) -> subprocess.CompletedProcess:
    """Run a command to completion (check=True), via Docker when applicable."""
    args = [str(c) for c in cmd]
    require(args[0])
    real = _docker_cmd(args) if _is_docker_tool(args[0]) else args
    log.debug("run: %s", " ".join(real))
    return subprocess.run(real, check=True, **kwargs)


def capture(cmd: list[str | Path]) -> str:
    """Run a command and return its stdout (stripped)."""
    return run(cmd, capture_output=True, text=True).stdout.strip()


def popen(cmd: list[str | Path], log_path: Path) -> subprocess.Popen:
    """Start a long-running background server (tile/route), output -> log_path.

    For Docker tools the container is force-removed first (clean restart) and its
    port published; terminating the returned process stops ``docker run`` and,
    via ``--rm``, the container.
    """
    args = [str(c) for c in cmd]
    require(args[0])
    if _is_docker_tool(args[0]):
        subprocess.run(
            ["docker", "rm", "-f", f"sbrmsp-{args[0]}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        real = _docker_cmd(args, server=True)
    else:
        real = args
    log.debug("spawn: %s (-> %s)", " ".join(real), log_path)
    fh = open(log_path, "w")
    return subprocess.Popen(real, stdout=fh, stderr=subprocess.STDOUT)
