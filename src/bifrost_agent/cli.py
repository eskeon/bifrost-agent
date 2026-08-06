"""CLI: bifrost tunnel install|uninstall|list|logs, bifrost version."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from bifrost_agent import __version__
from bifrost_agent.agent import run_forever
from bifrost_agent.config import (
    LEGACY_INSTANCE_ID,
    Config,
    instance_config_path,
    load,
)
from bifrost_agent.install_token import parse_install_token
from bifrost_agent.launchd import get_instance
from bifrost_agent.launchd import install as launchd_install
from bifrost_agent.launchd import list_instances
from bifrost_agent.launchd import log_path_for
from bifrost_agent.launchd import uninstall as launchd_uninstall
from bifrost_agent.launchd import uninstall_all


@click.group()
@click.version_option(__version__, prog_name="bifrost")
def main() -> None:
    """Bifrost tunnel agent."""


@main.group()
def tunnel() -> None:
    """Manage the path tunnel agent."""


@tunnel.command("install")
@click.argument("token")
def tunnel_install(token: str) -> None:
    """Install LaunchDaemon from a console install token (requires sudo)."""
    try:
        parsed = parse_install_token(token)
        cfg = Config(url=parsed.url, token=parsed.token, tunnel_id=parsed.tunnel_id)
        instance_id = launchd_install(cfg)
    except PermissionError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"installed instance {instance_id}")
    if cfg.tunnel_id:
        click.echo(f"tunnel: {cfg.tunnel_id}")
    click.echo(f"config: {instance_config_path(instance_id)}")
    click.echo(f"logs:   {log_path_for(instance_id)}")


@tunnel.command("uninstall")
@click.argument("instance_id", required=False)
@click.option("--all", "remove_all", is_flag=True, help="Remove every instance.")
def tunnel_uninstall(instance_id: str | None, remove_all: bool) -> None:
    """Remove one LaunchDaemon instance (or --all). Requires sudo."""
    if remove_all and instance_id:
        click.echo("error: pass either <id> or --all, not both", err=True)
        sys.exit(1)
    if not remove_all and not instance_id:
        click.echo("error: instance id required (or use --all)", err=True)
        click.echo("usage: sudo bifrost tunnel uninstall <id>", err=True)
        click.echo("       sudo bifrost tunnel uninstall --all", err=True)
        sys.exit(1)
    try:
        if remove_all:
            removed = uninstall_all()
            if not removed:
                click.echo("No tunnel agents installed.")
                return
            for rid in removed:
                click.echo(f"uninstalled {rid}")
            return
        assert instance_id is not None
        if get_instance(instance_id) is None:
            click.echo(f"error: unknown instance: {instance_id}", err=True)
            sys.exit(1)
        launchd_uninstall(instance_id)
    except PermissionError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"uninstalled {instance_id}")


@tunnel.command("list")
def tunnel_list() -> None:
    """Show installed tunnel agent instances."""
    rows = list_instances()
    if not rows:
        click.echo("No tunnel agents installed.")
        click.echo("Install with: sudo bifrost tunnel install <token>")
        return
    for i, row in enumerate(rows):
        if i > 0:
            click.echo("")
        click.echo(row.id)
        if row.tunnel_id:
            click.echo(f"  tunnel:  {row.tunnel_id}")
        click.echo(f"  state:   {_format_state(row.loaded)}")
        if row.url:
            click.echo(f"  url:     {row.url}")
        click.echo(f"  logs:    {row.log_path}")


def _format_state(running: bool) -> str:
    """Colored status indicator for terminal list output."""
    if running:
        dot = click.style("●", fg="green")
        label = click.style("running", fg="green")
    else:
        dot = click.style("●", fg="red")
        label = click.style("stopped", fg="red")
    return f"{dot} {label}"


@tunnel.command("logs")
@click.argument("instance_id")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (like tail -f).")
@click.option(
    "--lines",
    "-n",
    default=200,
    show_default=True,
    type=int,
    help="Number of lines to show (ignored with --follow after initial dump).",
)
def tunnel_logs(instance_id: str, follow: bool, lines: int) -> None:
    """Print logs for a specific instance."""
    row = get_instance(instance_id)
    if row is None:
        click.echo(f"error: unknown instance: {instance_id}", err=True)
        sys.exit(1)
    path = row.log_path
    if not path.is_file():
        click.echo(f"error: log file not found: {path}", err=True)
        sys.exit(1)
    try:
        _print_log_tail(path, lines=max(1, lines))
        if follow:
            _follow_log(path)
    except KeyboardInterrupt:
        return
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)


def _print_log_tail(path: Path, lines: int) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = text.splitlines()
    for line in parts[-lines:]:
        click.echo(line)


def _follow_log(path: Path) -> None:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                click.echo(line, nl=False)
                if not line.endswith("\n"):
                    click.echo("")
            else:
                time.sleep(0.25)


@tunnel.command("serve", hidden=True)
@click.option(
    "--instance",
    "instance_id",
    default=None,
    help="Instance id to serve (defaults to legacy single-instance config).",
)
def tunnel_serve(instance_id: str | None) -> None:
    """Background entrypoint for LaunchDaemon (not for interactive use)."""
    path = instance_config_path(instance_id or LEGACY_INSTANCE_ID)
    try:
        cfg = load(path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    run_forever(cfg, path)


@main.command("version")
def version_cmd() -> None:
    """Print version."""
    click.echo(__version__)


if __name__ == "__main__":
    main()
