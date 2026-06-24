"""Thin wrappers around the external binaries the pipeline shells out to
(osmium, tippecanoe, osrm-*, pmtiles). One place to check availability, log the
command and surface errors clearly."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def require(*binaries: str) -> None:
    """Raise a clear error if any binary is missing from PATH."""
    missing = [b for b in binaries if shutil.which(b) is None]
    if missing:
        raise RuntimeError(
            f"missing tool(s): {', '.join(missing)} — install with "
            f"`brew install osmium-tool tippecanoe pmtiles osrm-backend`"
        )


def run(cmd: list[str | Path], **kwargs) -> subprocess.CompletedProcess:
    """Run a command to completion (check=True)."""
    args = [str(c) for c in cmd]
    require(args[0])
    log.debug("run: %s", " ".join(args))
    return subprocess.run(args, check=True, **kwargs)


def capture(cmd: list[str | Path]) -> str:
    """Run a command and return its stdout (stripped)."""
    return run(cmd, capture_output=True, text=True).stdout.strip()


def popen(cmd: list[str | Path], log_path: Path) -> subprocess.Popen:
    """Start a long-running background process (e.g. a tile/route server),
    redirecting its output to log_path."""
    args = [str(c) for c in cmd]
    require(args[0])
    log.debug("spawn: %s (-> %s)", " ".join(args), log_path)
    fh = open(log_path, "w")
    return subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT)
