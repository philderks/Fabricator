"""Fabricator CLI — system-level commands for managing the Fabricator service."""
import json
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
SYSTEMD_UNIT = f"/etc/systemd/system/{SERVICE_NAME}.service"
DATA_DIR = "/var/lib/fabricator"
CONFIG_DIR = "/etc/fabricator"
SERVICE_USER = "fabricator"
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
def main():
    """Fabricator service management."""


@main.command()
def start():
    """Start the Fabricator service."""
    click.echo("Starting Fabricator...")
    rc = _systemctl("start")
    if rc == 0:
        click.echo(click.style("Fabricator started successfully.", fg="green"))
    else:
        click.echo(click.style("Failed to start Fabricator.", fg="red"))
        sys.exit(rc)


@main.command()
def stop():
    """Stop the Fabricator service (graceful shutdown attempt first)."""
    click.echo("Stopping Fabricator...")

    rc = _systemctl("stop")
    if rc == 0:
        click.echo(click.style("Fabricator stopped successfully.", fg="green"))
    else:
        click.echo(click.style("Failed to stop Fabricator.", fg="red"))
        sys.exit(rc)


@main.command()
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


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _collect_status() -> dict:
    """Return a dict with systemd state and Flask/API reachability info."""
    result = subprocess.run(
        ["systemctl", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    systemd_state = result.stdout.strip() or "unknown"

    flask_up = False
    servers: "list | None" = None

    # /api/health is the always-available liveness endpoint (open even in the
    # setup/locked states). The old code hit a non-existent /api/status, which
    # the catch-all turned into a JSON 404 — so Flask looked "up" but the status
    # view could never show anything useful.
    try:
        health = requests.get(f"{API_BASE}/api/health", timeout=5)
        flask_up = bool(health.ok)
    except Exception:
        flask_up = False

    if flask_up:
        try:
            resp = requests.get(f"{API_BASE}/api/servers", timeout=5)
            if resp.ok:
                body = resp.json()
                if isinstance(body, list):
                    servers = body
        except Exception:
            servers = None

    return {
        "systemd_state": systemd_state,
        "flask_up": flask_up,
        "servers": servers,
    }


def _render_status(data: dict) -> None:
    """Print a human-readable status summary."""
    state = data["systemd_state"]
    state_color = "green" if state == "active" else "red"
    click.echo(f"Service:  {click.style(state, fg=state_color)}")

    if not data["flask_up"]:
        click.echo(f"Flask:    {click.style('down', fg='red')}")
        return

    click.echo(f"Flask:    {click.style('up', fg='green')}")

    servers = data.get("servers")
    if servers is None:
        click.echo("  (could not read the server list)")
        return

    def _running(server: dict) -> bool:
        return ((server.get("runtime") or {}).get("status") or server.get("status")) == "running"

    running = [s for s in servers if _running(s)]
    click.echo(f"Servers:  {len(running)}/{len(servers)} running")
    for server in running:
        click.echo(f"  • {server.get('name') or server.get('id') or '?'}")


@main.command()
@click.option(
    "--json", "as_json",
    is_flag=True,
    help="Output raw JSON instead of formatted text.",
)
def status(as_json: bool) -> None:
    """Show the systemd service state and Flask/Minecraft API status."""
    data = _collect_status()
    if as_json:
        click.echo(json.dumps(data))
    else:
        _render_status(data)


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

def _collect_version() -> dict:
    """Return a dict with the installed version string (or null)."""
    return {"version": _get_local_version()}


def _render_version(data: dict) -> None:
    """Print the installed version in a human-readable form."""
    ver = data["version"]
    if ver:
        click.echo(f"Fabricator {ver}")
    else:
        click.echo(
            click.style(
                f"Version unknown — version file not found at {VERSION_FILE}",
                fg="yellow",
            )
        )


@main.command()
@click.option(
    "--json", "as_json",
    is_flag=True,
    help="Output raw JSON instead of formatted text.",
)
def version(as_json: bool) -> None:
    """Print the installed Fabricator version read from the version marker file."""
    data = _collect_version()
    if as_json:
        click.echo(json.dumps(data))
    else:
        _render_version(data)


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def _uninstall_step(label: str, *cmd: str) -> None:
    """Run a single removal step, printing progress and tolerating failures."""
    click.echo(f"  {label}...", nl=False)
    try:
        result = subprocess.run(list(cmd), capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(click.style(" done", fg="green"))
        else:
            msg = (result.stderr or result.stdout).strip()
            click.echo(
                click.style(f" warning: {msg or 'non-zero exit'}", fg="yellow")
            )
    except Exception as exc:
        click.echo(click.style(f" warning: {exc}", fg="yellow"))


@main.command()
def uninstall() -> None:
    """Remove Fabricator, its data, config, systemd unit, and service user."""
    confirmation = click.prompt(
        "This will remove Fabricator and all its data. Type 'yes' to continue"
    )
    if confirmation.strip().lower() != "yes":
        click.echo("Aborted.")
        return

    click.echo("\nUninstalling Fabricator...")

    _uninstall_step("Stopping service",    "systemctl", "stop",    SERVICE_NAME)
    _uninstall_step("Disabling service",   "systemctl", "disable", SERVICE_NAME)
    _uninstall_step("Removing app files",  "rm", "-rf", INSTALL_DIR)
    _uninstall_step("Removing data dir",   "rm", "-rf", DATA_DIR)
    _uninstall_step("Removing config dir", "rm", "-rf", CONFIG_DIR)
    _uninstall_step("Removing service user", "userdel", SERVICE_USER)
    _uninstall_step("Removing systemd unit", "rm", "-f", SYSTEMD_UNIT)
    _uninstall_step("Reloading systemd",   "systemctl", "daemon-reload")

    click.echo(click.style("\nFabricator uninstalled.", fg="green"))


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------

def _collect_help() -> list[dict]:
    """Return a list of {command, description} dicts for all registered commands."""
    return [
        {"command": name, "description": cmd.get_short_help_str()}
        for name, cmd in sorted(main.commands.items())
    ]


def _render_help(data: list[dict]) -> None:
    """Print a formatted table of all commands and their descriptions."""
    if not data:
        return
    width = max(len(item["command"]) for item in data)
    click.echo("Commands:")
    for item in data:
        click.echo(f"  {item['command']:<{width}}  {item['description']}")


@main.command(name="help")
@click.option(
    "--json", "as_json",
    is_flag=True,
    help="Output raw JSON instead of formatted text.",
)
def help_cmd(as_json: bool) -> None:
    """Show a summary of every available command and what it does."""
    data = _collect_help()
    if as_json:
        click.echo(json.dumps(data))
    else:
        _render_help(data)


# ---------------------------------------------------------------------------
# hash-password
# ---------------------------------------------------------------------------

@main.command(name="hash-password")
def hash_password_cmd() -> None:
    """Generate a password hash for FABRICATOR_AUTH_PASSWORD_HASH."""
    import sys
    from pathlib import Path

    # Make `backend` importable in both layouts:
    # - source checkout: repo/apps/backend
    # - installed release: $APP_DIR/backend
    root = Path(__file__).resolve().parents[3]
    for candidate in (root, root / "apps"):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    from backend.auth.service import hash_password

    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    click.echo(hash_password(password))
