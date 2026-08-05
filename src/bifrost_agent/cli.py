"""CLI: bifrost tunnel install|run|uninstall, bifrost version."""

from __future__ import annotations

import sys

import click

from bifrost_agent import __version__
from bifrost_agent.agent import run_forever
from bifrost_agent.config import Config, default_config_path, load, save, user_config_path
from bifrost_agent.install_token import parse_install_token
from bifrost_agent.launchd import install as launchd_install
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


@tunnel.command("run")
@click.argument("token", required=False)
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
def tunnel_run(token: str | None, config_path: str | None) -> None:
    """Run the agent in the foreground."""
    try:
        if token:
            parsed = parse_install_token(token)
            cfg = Config(url=parsed.url, token=parsed.token)
            # Convenience: persist to user config when not root.
            if config_path:
                from pathlib import Path

                save(cfg, Path(config_path))
            else:
                try:
                    save(cfg, user_config_path())
                except OSError:
                    pass
        elif config_path:
            from pathlib import Path

            cfg = load(Path(config_path))
        else:
            cfg = load(default_config_path())
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
