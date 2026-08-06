"""Parse Cloudflare-style opaque install tokens from the Bifrost console."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class InstallToken:
    url: str
    token: str
    tunnel_id: int | None = None


def parse_install_token(raw: str) -> InstallToken:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("install token is required")

    # Allow pasting the full command by accident.
    if raw.startswith("sudo "):
        parts = raw.split()
        raw = parts[-1] if parts else raw

    pad = "=" * (-len(raw) % 4)
    try:
        data = base64.urlsafe_b64decode(raw + pad)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid install token encoding") from exc

    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid install token json") from exc

    if not isinstance(obj, dict):
        raise ValueError("invalid install token")
    url = str(obj.get("url") or "").strip()
    token = str(obj.get("token") or "").strip()
    if not url or not token:
        raise ValueError("install token missing url or token")
    tunnel_id = None
    raw_tid = obj.get("tunnel_id")
    if raw_tid is not None and raw_tid != "":
        try:
            n = int(raw_tid)
            if n > 0:
                tunnel_id = n
        except (TypeError, ValueError):
            tunnel_id = None
    return InstallToken(url=url, token=token, tunnel_id=tunnel_id)
