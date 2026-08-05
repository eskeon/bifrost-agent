"""CLI: bifrost tunnel install|uninstall|list, bifrost version."""

from __future__ import annotations

import sys

import click

from bifrost_agent import __version__
from bifrost_agent.agent import run_forever
from bifrost_agent.config import Config, SYSTEM_CONFIG, load
from bifrost_agent.install_token import parse_install_token
from bifrost_agent.launchd import install as launchd_install
from bifrost_agent.launchd import list_instances
from bifrost_agent.launchd import uninstall as launchd_uninstall


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
        cfg = Config(url=parsed.url, token=parsed.token)
        launchd_install(cfg)
    except PermissionError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo("installed LaunchDaemon com.bifrost.tunnel")
    click.echo("config: /Library/Application Support/bifrost/config.json")
    click.echo("logs:   /Library/Logs/bifrost-tunnel.log")


@tunnel.command("uninstall")
def tunnel_uninstall() -> None:
    """Remove LaunchDaemon and system config (requires sudo)."""
    try:
        launchd_uninstall()
    except PermissionError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo("uninstalled com.bifrost.tunnel")


@tunnel.command("list")
def tunnel_list() -> None:
    """Show installed tunnel agent instances."""
    rows = list_instances()
    if not rows:
        click.echo("No tunnel agents installed.")
        click.echo("Install with: sudo bifrost tunnel install <token>")
        return
    for i, row in enumerate(rows, 1):
        if i > 1:
            click.echo("")
        state = "running" if row.loaded else ("installed" if row.installed else "config-only")
        click.echo(f"{row.label}")
        click.echo(f"  state:   {state}")
        click.echo(f"  plist:   {row.plist_path}")
        click.echo(f"  config:  {row.config_path}")
        click.echo(f"  logs:    {row.log_path}")
        if row.url:
            click.echo(f"  url:     {row.url}")
        if row.token_preview:
            click.echo(f"  token:   {row.token_preview}")


@tunnel.command("serve", hidden=True)
def tunnel_serve() -> None:
    """Background entrypoint for LaunchDaemon (not for interactive use)."""
    try:
        cfg = load(SYSTEM_CONFIG)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    run_forever(cfg)


@main.command("version")
def version_cmd() -> None:
    """Print version."""
    click.echo(__version__)


if __name__ == "__main__":
    main()
