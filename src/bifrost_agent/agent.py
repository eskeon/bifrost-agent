"""WebSocket tunnel agent — forwards Bifrost http_req frames to local_url."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import websockets

from pathlib import Path

from bifrost_agent import __version__
from bifrost_agent.config import Config, save

log = logging.getLogger("bifrost.agent")

MAX_BODY = 8 << 20
SUBPROTOCOL = "bifrost-tunnel"


def _ws_url(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


def _join_local(local_url: str, path: str, query: str) -> str:
    base = local_url.rstrip("/") + "/"
    rel = (path or "/").lstrip("/")
    target = urljoin(base, rel)
    if query:
        sep = "&" if "?" in target else "?"
        target = f"{target}{sep}{query}"
    return target


async def _forward(client: httpx.AsyncClient, msg: dict[str, Any]) -> dict[str, Any]:
    req_id = str(msg.get("id") or "")
    local_url = str(msg.get("local_url") or "").strip()
    if not local_url:
        return {
            "type": "http_res",
            "id": req_id,
            "status": 502,
            "error": "missing local_url",
        }
    parsed = urlparse(local_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {
            "type": "http_res",
            "id": req_id,
            "status": 502,
            "error": "invalid local_url",
        }

    method = str(msg.get("method") or "GET").upper()
    path = str(msg.get("path") or "/")
    query = str(msg.get("query") or "")
    headers_in = msg.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(headers_in, dict):
        for k, vals in headers_in.items():
            if str(k).lower() in {
                "host",
                "content-length",
                "connection",
                "transfer-encoding",
                "keep-alive",
                "upgrade",
            }:
                continue
            if isinstance(vals, list) and vals:
                headers[str(k)] = str(vals[0])
            elif isinstance(vals, str):
                headers[str(k)] = vals

    body = b""
    if msg.get("body"):
        try:
            body = base64.b64decode(msg["body"])
        except Exception:  # noqa: BLE001
            return {
                "type": "http_res",
                "id": req_id,
                "status": 502,
                "error": "invalid body encoding",
            }
        if len(body) > MAX_BODY:
            return {
                "type": "http_res",
                "id": req_id,
                "status": 413,
                "error": "body too large",
            }

    url = _join_local(local_url, path, query)
    try:
        resp = await client.request(method, url, headers=headers, content=body)
    except Exception as exc:  # noqa: BLE001
        return {
            "type": "http_res",
            "id": req_id,
            "status": 502,
            "error": str(exc),
        }

    out_headers: dict[str, list[str]] = {}
    for k, v in resp.headers.multi_items():
        if k.lower() in {"transfer-encoding", "connection", "content-encoding"}:
            continue
        out_headers.setdefault(k, []).append(v)

    resp_body = resp.content
    if len(resp_body) > MAX_BODY:
        return {
            "type": "http_res",
            "id": req_id,
            "status": 502,
            "error": "response too large",
        }

    return {
        "type": "http_res",
        "id": req_id,
        "status": resp.status_code,
        "headers": out_headers,
        "body": base64.b64encode(resp_body).decode("ascii") if resp_body else "",
    }


def _persist_tunnel_id(cfg: Config, config_path: Path | None, tunnel_id: object) -> None:
    """Remember console tunnel id in config so `bifrost tunnel list` can show it."""
    try:
        tid = int(tunnel_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if tid <= 0 or cfg.tunnel_id == tid:
        return
    cfg.tunnel_id = tid
    if config_path is None:
        return
    try:
        save(cfg, config_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not persist tunnel_id=%s: %s", tid, exc)


async def _session(cfg: Config, config_path: Path | None = None) -> None:
    url = _ws_url(cfg.url)
    async with websockets.connect(
        url,
        subprotocols=[SUBPROTOCOL],
        max_size=MAX_BODY + (1 << 20),
        ping_interval=None,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "token": cfg.token,
                    "version": __version__,
                }
            )
        )
        welcome_raw = await ws.recv()
        welcome = json.loads(welcome_raw)
        if welcome.get("type") != "welcome":
            raise RuntimeError(f"expected welcome, got {welcome.get('type')!r}")
        log.info(
            "connected tunnel_id=%s name=%r",
            welcome.get("tunnel_id"),
            welcome.get("name"),
        )
        _persist_tunnel_id(cfg, config_path, welcome.get("tunnel_id"))

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("bad frame")
                    continue
                typ = msg.get("type")
                if typ == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif typ == "http_req":
                    res = await _forward(client, msg)
                    await ws.send(json.dumps(res))
                elif typ == "error":
                    log.error("server error: %s", msg.get("message"))
                else:
                    log.debug("ignore type=%s", typ)


async def run(cfg: Config, config_path: Path | None = None) -> None:
    cfg.validate()
    backoff = 1.0
    while True:
        try:
            await _session(cfg, config_path)
            backoff = 1.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("disconnected: %s; reconnecting in %.0fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def run_forever(cfg: Config, config_path: Path | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        asyncio.run(run(cfg, config_path))
    except KeyboardInterrupt:
        pass
