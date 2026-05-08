"""Fabricator CLI — system-level commands for managing the Fabricator service."""
import subprocess
import sys
from pathlib import Path

import click
import requests

INSTALL_DIR = "/opt/fabricator"
APP_DIR = f"{INSTALL_DIR}/app"
VERSION_FILE = f"{APP_DIR}/.fabricator_version"
INSTALL_SCRIPT = f"{APP_DIR}/tools/install.sh"
SERVICE_NAME = "fabricator"
API_BASE = "http://localhost:5000"
GITHUB_API = "https://api.github.com/repos/philderks/Fabricator/releases/latest"


def _systemctl(action: str) -> int:
    result = subprocess.run(
        ["systemctl", action, SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    return result.returncode


def _get_local_version() -> str | None:
    path = Path(VERSION_FILE)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _get_latest_release_tag() -> str | None:
    try:
        resp = requests.get(GITHUB_API, timeout=15)
        resp.raise_for_status()
        return resp.json().get("tag_name")
    except Exception:
        return None


@click.group()
def cli():
    """Fabricator service management."""


@cli.command()
def start():
    """Start the Fabricator service."""
    click.echo("Starting Fabricator...")
    rc = _systemctl("start")
    if rc == 0:
        click.echo(click.style("Fabricator started successfully.", fg="green"))
    else:
        click.echo(click.style("Failed to start Fabricator.", fg="red"))
        sys.exit(rc)


@cli.command()
def stop():
    """Stop the Fabricator service (graceful shutdown attempt first)."""
    click.echo("Stopping Fabricator...")

    try:
        requests.post(f"{API_BASE}/api/stop", timeout=10)
    except Exception:
        pass

    rc = _systemctl("stop")
    if rc == 0:
        click.echo(click.style("Fabricator stopped successfully.", fg="green"))
    else:
        click.echo(click.style("Failed to stop Fabricator.", fg="red"))
        sys.exit(rc)


@cli.command()
def update():
    """Update Fabricator to the latest release."""
    local_version = _get_local_version()
    click.echo(f"Current version: {local_version or 'unknown'}")

    click.echo("Checking for updates...")
    latest_tag = _get_latest_release_tag()

    if latest_tag is None:
        click.echo(click.style(
            "Could not determine latest release. Check your network or try again later.",
            fg="red",
        ))
        sys.exit(1)

    if local_version and local_version == latest_tag:
        click.echo(click.style(f"Already up to date ({latest_tag}).", fg="green"))
        return

    click.echo(f"Updating from {local_version or 'unknown'} to {latest_tag}...")

    result = subprocess.run(
        ["bash", INSTALL_SCRIPT, "--update"],
        env={**__import__("os").environ, "FABRICATOR_VERSION": latest_tag},
    )

    if result.returncode == 0:
        click.echo(click.style(f"Successfully updated to {latest_tag}.", fg="green"))
    else:
        click.echo(click.style("Update failed. Check output above for details.", fg="red"))
        sys.exit(result.returncode)
