"""macOS LaunchDaemon install/uninstall/list for multi-instance tunnel agents."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bifrost_agent.config import (
    INSTANCES_ROOT,
    LEGACY_INSTANCE_ID,
    LEGACY_SYSTEM_CONFIG,
    Config,
    instance_config_path,
    instance_id_for_token,
    load,
    save,
)

LABEL_PREFIX = "com.bifrost.tunnel"
LEGACY_LABEL = LABEL_PREFIX
LEGACY_PLIST_PATH = Path("/Library/LaunchDaemons") / f"{LEGACY_LABEL}.plist"
LEGACY_LOG_PATH = Path("/Library/Logs/bifrost-tunnel.log")
LAUNCH_DAEMONS = Path("/Library/LaunchDaemons")
LOGS_DIR = Path("/Library/Logs")


@dataclass
class InstanceInfo:
    id: str
    label: str
    plist_path: Path
    config_path: Path
    log_path: Path
    installed: bool
    loaded: bool
    url: str
    tunnel_id: int | None = None


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


def label_for(instance_id: str) -> str:
    if instance_id == LEGACY_INSTANCE_ID:
        return LEGACY_LABEL
    return f"{LABEL_PREFIX}.{instance_id}"


def plist_path_for(instance_id: str) -> Path:
    if instance_id == LEGACY_INSTANCE_ID:
        return LEGACY_PLIST_PATH
    return LAUNCH_DAEMONS / f"{LABEL_PREFIX}.{instance_id}.plist"


def log_path_for(instance_id: str) -> Path:
    if instance_id == LEGACY_INSTANCE_ID:
        return LEGACY_LOG_PATH
    return LOGS_DIR / f"bifrost-tunnel-{instance_id}.log"


def _daemon_program(instance_id: str) -> list[str]:
    bin_path = _bifrost_bin()
    if Path(bin_path).name.startswith("python"):
        return [
            bin_path,
            "-m",
            "bifrost_agent",
            "tunnel",
            "serve",
            "--instance",
            instance_id,
        ]
    return [bin_path, "tunnel", "serve", "--instance", instance_id]


def _is_loaded(label: str) -> bool:
    proc = subprocess.run(
        ["launchctl", "print", f"system/{label}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _bootout(label: str) -> None:
    subprocess.run(
        ["launchctl", "bootout", f"system/{label}"],
        check=False,
        capture_output=True,
    )


def _load_config_meta(path: Path) -> tuple[str, int | None]:
    if not path.is_file():
        return "", None
    try:
        cfg = load(path)
        return cfg.url, cfg.tunnel_id
    except Exception:  # noqa: BLE001
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            url = str(raw.get("url") or "")
            tid_raw = raw.get("tunnel_id")
            tid: int | None = None
            if tid_raw is not None and tid_raw != "":
                try:
                    n = int(tid_raw)
                    if n > 0:
                        tid = n
                except (TypeError, ValueError):
                    tid = None
            return url, tid
        except Exception:  # noqa: BLE001
            return "", None


def install(cfg: Config) -> str:
    """Install or replace one instance. Returns instance id."""
    _require_root()
    instance_id = instance_id_for_token(cfg.token)
    label = label_for(instance_id)
    plist_path = plist_path_for(instance_id)
    log_path = log_path_for(instance_id)
    config_path = instance_config_path(instance_id)

    save(cfg, config_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": label,
        "ProgramArguments": _daemon_program(instance_id),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)
    os.chmod(plist_path, 0o644)

    _bootout(label)
    subprocess.run(
        ["launchctl", "bootstrap", "system", str(plist_path)],
        check=True,
    )
    subprocess.run(["launchctl", "enable", f"system/{label}"], check=False)
    subprocess.run(["launchctl", "kickstart", "-k", f"system/{label}"], check=False)
    return instance_id


def uninstall(instance_id: str) -> None:
    """Remove one instance by id (including legacy)."""
    _require_root()
    if not instance_id:
        raise ValueError("instance id is required")

    label = label_for(instance_id)
    plist_path = plist_path_for(instance_id)
    config_path = instance_config_path(instance_id)

    _bootout(label)
    if plist_path.exists():
        plist_path.unlink()
    if config_path.exists():
        config_path.unlink()
    # Remove empty instance directory (not legacy support root).
    if instance_id != LEGACY_INSTANCE_ID:
        parent = config_path.parent
        if parent.is_dir() and parent != INSTANCES_ROOT:
            try:
                parent.rmdir()
            except OSError:
                pass


def uninstall_all() -> list[str]:
    """Remove every known instance. Returns removed ids."""
    _require_root()
    ids = [row.id for row in list_instances()]
    for instance_id in ids:
        uninstall(instance_id)
    return ids


def get_instance(instance_id: str) -> InstanceInfo | None:
    for row in list_instances():
        if row.id == instance_id:
            return row
    return None


def list_instances() -> list[InstanceInfo]:
    """Return all installed tunnel agent instances (multi + legacy)."""
    seen: set[str] = set()
    rows: list[InstanceInfo] = []

    # Multi-instance plists: com.bifrost.tunnel.<id>.plist
    if LAUNCH_DAEMONS.is_dir():
        prefix = f"{LABEL_PREFIX}."
        for plist in sorted(LAUNCH_DAEMONS.glob(f"{LABEL_PREFIX}.*.plist")):
            name = plist.name
            if not name.startswith(prefix) or not name.endswith(".plist"):
                continue
            instance_id = name[len(prefix) : -len(".plist")]
            if not instance_id or instance_id in seen:
                continue
            seen.add(instance_id)
            rows.append(_info_for(instance_id))

    # Config dirs without plist yet
    if INSTANCES_ROOT.is_dir():
        for child in sorted(INSTANCES_ROOT.iterdir()):
            if not child.is_dir():
                continue
            instance_id = child.name
            if instance_id in seen:
                continue
            cfg = child / "config.json"
            if not cfg.is_file():
                continue
            seen.add(instance_id)
            rows.append(_info_for(instance_id))

    # Legacy single-instance
    if LEGACY_PLIST_PATH.is_file() or LEGACY_SYSTEM_CONFIG.is_file():
        if LEGACY_INSTANCE_ID not in seen:
            rows.append(_info_for(LEGACY_INSTANCE_ID))

    rows.sort(key=lambda r: r.id)
    return rows


def _info_for(instance_id: str) -> InstanceInfo:
    label = label_for(instance_id)
    plist_path = plist_path_for(instance_id)
    config_path = instance_config_path(instance_id)
    log_path = log_path_for(instance_id)
    installed = plist_path.is_file()
    loaded = _is_loaded(label) if installed else False
    url, tunnel_id = _load_config_meta(config_path)
    return InstanceInfo(
        id=instance_id,
        label=label,
        plist_path=plist_path,
        config_path=config_path,
        log_path=log_path,
        installed=installed,
        loaded=loaded,
        url=url,
        tunnel_id=tunnel_id,
    )
