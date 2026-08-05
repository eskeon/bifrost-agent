"""macOS LaunchDaemon install/uninstall for the tunnel agent."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from bifrost_agent.config import SYSTEM_CONFIG, Config, save

LABEL = "com.bifrost.tunnel"
PLIST_PATH = Path("/Library/LaunchDaemons") / f"{LABEL}.plist"
LOG_PATH = Path("/Library/Logs/bifrost-tunnel.log")


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("this command requires root (use sudo)")


def _bifrost_bin() -> str:
    # Prefer the invoking executable (works under `sudo bifrost …`).
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.is_file() and os.access(argv0, os.X_OK):
        return str(argv0)
    found = shutil.which("bifrost")
    if found:
        return found
    return sys.executable


def install(cfg: Config) -> None:
    _require_root()
    save(cfg, SYSTEM_CONFIG)

    bin_path = _bifrost_bin()
    # If invoked as `python -m bifrost_agent`, run via module.
    if Path(bin_path).name.startswith("python"):
        program = [bin_path, "-m", "bifrost_agent", "tunnel", "run"]
    else:
        program = [bin_path, "tunnel", "run"]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": program,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_PATH),
        "StandardErrorPath": str(LOG_PATH),
    }
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as f:
        plistlib.dump(plist, f)
    os.chmod(PLIST_PATH, 0o644)

    # bootout if already loaded, then bootstrap
    subprocess.run(
        ["launchctl", "bootout", f"system/{LABEL}"],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", "system", str(PLIST_PATH)],
        check=True,
    )
    subprocess.run(["launchctl", "enable", f"system/{LABEL}"], check=False)
    subprocess.run(["launchctl", "kickstart", "-k", f"system/{LABEL}"], check=False)


def uninstall() -> None:
    _require_root()
    subprocess.run(
        ["launchctl", "bootout", f"system/{LABEL}"],
        check=False,
        capture_output=True,
    )
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    if SYSTEM_CONFIG.exists():
        SYSTEM_CONFIG.unlink()
