"""Agent config (url + auth token only — local upstreams come from Bifrost)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


SUPPORT_ROOT = Path("/Library/Application Support/bifrost")
INSTANCES_ROOT = SUPPORT_ROOT / "instances"
# Pre-0.2.0 single-instance layout
LEGACY_SYSTEM_CONFIG = SUPPORT_ROOT / "config.json"
LEGACY_INSTANCE_ID = "legacy"


@dataclass
class Config:
    url: str
    token: str
    tunnel_id: int | None = None

    def validate(self) -> None:
        if not (self.url or "").strip():
            raise ValueError("url is required")
        if not (self.token or "").strip():
            raise ValueError("token is required")


def instance_id_for_token(token: str) -> str:
    """Stable short id from auth token (available at install time)."""
    digest = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    return digest[:12]


def instance_config_path(instance_id: str) -> Path:
    if instance_id == LEGACY_INSTANCE_ID:
        return LEGACY_SYSTEM_CONFIG
    return INSTANCES_ROOT / instance_id / "config.json"


def user_config_path() -> Path:
    home = Path.home()
    return home / "Library" / "Application Support" / "bifrost" / "config.json"


def default_config_path() -> Path:
    """Prefer a readable system instance config, else user config."""
    if INSTANCES_ROOT.is_dir():
        for child in sorted(INSTANCES_ROOT.iterdir()):
            cfg = child / "config.json"
            if cfg.is_file() and os.access(cfg, os.R_OK):
                return cfg
    if LEGACY_SYSTEM_CONFIG.is_file() and os.access(LEGACY_SYSTEM_CONFIG, os.R_OK):
        return LEGACY_SYSTEM_CONFIG
    return user_config_path()


def _parse_tunnel_id(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def load(path: Path | None = None) -> Config:
    p = path or default_config_path()
    if not p.is_file():
        raise FileNotFoundError(f"config not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    cfg = Config(
        url=str(data.get("url") or ""),
        token=str(data.get("token") or ""),
        tunnel_id=_parse_tunnel_id(data.get("tunnel_id")),
    )
    cfg.validate()
    return cfg


def save(cfg: Config, path: Path) -> None:
    cfg.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(cfg)
    if payload.get("tunnel_id") is None:
        payload.pop("tunnel_id", None)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
