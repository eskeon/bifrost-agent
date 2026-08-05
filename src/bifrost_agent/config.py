"""Agent config (url + auth token only — local upstreams come from Bifrost)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


SYSTEM_CONFIG = Path("/Library/Application Support/bifrost/config.json")


@dataclass
class Config:
    url: str
    token: str

    def validate(self) -> None:
        if not (self.url or "").strip():
            raise ValueError("url is required")
        if not (self.token or "").strip():
            raise ValueError("token is required")


def user_config_path() -> Path:
    home = Path.home()
    return home / "Library" / "Application Support" / "bifrost" / "config.json"


def default_config_path() -> Path:
    """Prefer system config when readable (LaunchDaemon), else user config."""
    if SYSTEM_CONFIG.is_file() and os.access(SYSTEM_CONFIG, os.R_OK):
        return SYSTEM_CONFIG
    return user_config_path()


def load(path: Path | None = None) -> Config:
    p = path or default_config_path()
    if not p.is_file():
        raise FileNotFoundError(f"config not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    cfg = Config(url=str(data.get("url") or ""), token=str(data.get("token") or ""))
    cfg.validate()
    return cfg


def save(cfg: Config, path: Path) -> None:
    cfg.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
