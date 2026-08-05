"""macOS LaunchDaemon install/uninstall/list for the tunnel agent."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bifrost_agent.config import SYSTEM_CONFIG, Config, load, save

LABEL = "com.bifrost.tunnel"
PLIST_PATH = Path("/Library/LaunchDaemons") / f"{LABEL}.plist"
LOG_PATH = Path("/Library/Logs/bifrost-tunnel.log")


@dataclass
class InstanceInfo:
    label: str
    plist_path: Path
    config_path: Path
    log_path: Path
    installed: bool
    loaded: bool
    url: str
    token_preview: str


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("this command requires root (use sudo)")


def _bifrost_bin() -> str:
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.is_file() and os.access(argv0, os.X_OK):
        return str(argv0)
    found = shutil.which("bifrost")
    if found:
        return found
    return sys.executable


def _daemon_program() -> list[str]:
    bin_path = _bifrost_bin()
    # Hidden `serve` entrypoint used only by LaunchDaemon.
    if Path(bin_path).name.startswith("python"):
        return [bin_path, "-m", "bifrost_agent", "tunnel", "serve"]
    return [bin_path, "tunnel", "serve"]


def install(cfg: Config) -> None:
    _require_root()
    save(cfg, SYSTEM_CONFIG)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": _daemon_program(),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_PATH),
        "StandardErrorPath": str(LOG_PATH),
    }
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as f:
        plistlib.dump(plist, f)
    os.chmod(PLIST_PATH, 0o644)

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


def _is_loaded() -> bool:
    proc = subprocess.run(
        ["launchctl", "print", f"system/{LABEL}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _mask_token(token: str) -> str:
    token = (token or "").strip()
    if len(token) <= 10:
        return "***" if token else ""
    return token[:6] + "…" + token[-4:]


def list_instances() -> list[InstanceInfo]:
    """Return installed tunnel agent instances (currently at most one system daemon)."""
    installed = PLIST_PATH.is_file()
    loaded = _is_loaded() if installed else False
    url = ""
    token_preview = ""
    if SYSTEM_CONFIG.is_file():
        try:
            cfg = load(SYSTEM_CONFIG)
            url = cfg.url
            token_preview = _mask_token(cfg.token)
        except Exception:  # noqa: BLE001
            try:
                raw = json.loads(SYSTEM_CONFIG.read_text(encoding="utf-8"))
                url = str(raw.get("url") or "")
                token_preview = _mask_token(str(raw.get("token") or ""))
            except Exception:  # noqa: BLE001
                pass

    if not installed and not SYSTEM_CONFIG.is_file():
        return []

    return [
        InstanceInfo(
            label=LABEL,
            plist_path=PLIST_PATH,
            config_path=SYSTEM_CONFIG,
            log_path=LOG_PATH,
            installed=installed,
            loaded=loaded,
            url=url,
            token_preview=token_preview,
        )
    ]
