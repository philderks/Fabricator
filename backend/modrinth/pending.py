"""Modpack installs that outlive the browser that asked for one.

Creating a server with a modpack is two jobs: install the loader, then install
the pack onto it. Only the first ran on the server. The browser polled the
loader install to completion and *then* issued the modpack install as a
separate request, so if the tab was gone at that moment — a refresh, a closed
screen, a laptop lid — nobody ever issued it. The loader finished, the server
record looked healthy, and the pack was silently dropped (issue #63). NeoForge
made it easy to hit: its install takes minutes, and the Close button on that
screen says "continues in background", which was true of the loader and false
of the pack.

This module is the pack half of that pipeline, expressed so the install worker
can run it with no HTTP request in flight and nobody to ask questions of:

* :func:`normalize_intent` turns the create request's ``modpack`` block into a
  record that can be stored on the server and replayed later.
* :func:`install` performs it, reporting progress through a callback.

Nothing here prompts. A pack whose mods cannot be classified installs with the
non-blocking defaults and reports the warnings in its result, for the dashboard
to surface once the user is back — an interactive 409 would strand a
half-created server with no way to answer it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.modrinth import mrpack
from backend.utils.time import iso_z_now

logger = logging.getLogger(__name__)

# Sources a stored intent can name. ``project`` is a pack on Modrinth,
# ``upload`` a .mrpack the user supplied (#53).
SOURCES = ("project", "upload")


class PendingModpackError(Exception):
    """Raised when a stored intent cannot be installed."""


def normalize_intent(raw: Any) -> Optional[Dict[str, Any]]:
    """Validate a create request's ``modpack`` block, or return None.

    Returns None for anything that does not name an installable pack, so a
    caller can treat "no modpack requested" and "modpack block was junk"
    identically: create the server without one. Only fields the install
    actually uses are kept — this is persisted on the server record, and
    echoing arbitrary client JSON back into storage is how that record grows
    fields nobody can account for.
    """
    if not isinstance(raw, dict):
        return None

    source = str(raw.get("source") or "").strip().lower()
    if source not in SOURCES:
        return None

    intent: Dict[str, Any] = {
        "source": source,
        "loader": str(raw.get("loader") or "").strip(),
        "mc_version": str(raw.get("mc_version") or "").strip(),
        "requested_at": iso_z_now(),
    }

    if source == "project":
        project_id = str(raw.get("project_id") or "").strip()
        if not project_id:
            return None
        intent["project_id"] = project_id
    else:
        upload_id = str(raw.get("upload_id") or "").strip()
        if not upload_id:
            return None
        intent["upload_id"] = upload_id

    overrides = raw.get("mod_side_overrides")
    if isinstance(overrides, dict):
        intent["mod_side_overrides"] = {
            str(k): str(v) for k, v in overrides.items()
            if str(v).strip().lower() in ("client", "server")
        }

    return intent


def describe(intent: Dict[str, Any]) -> str:
    """A short label for logs and progress detail."""
    if intent.get("source") == "upload":
        return intent.get("filename") or "uploaded modpack"
    return intent.get("project_id") or "modpack"


def install(
    client: Any,
    intent: Dict[str, Any],
    install_path: Path,
    progress_callback: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """Install the pack ``intent`` names into ``install_path``.

    ``clean_install`` is deliberately not honoured here: this runs on a server
    that was created moments ago, so there is nothing to clean and no backup
    worth taking. The interactive install route keeps both options for packs
    going onto a server that already has content.

    Raises :class:`PendingModpackError` when the intent can no longer be
    installed — most often a staged upload that expired or was swept.
    """
    source = intent.get("source")

    if source == "upload":
        upload_id = intent.get("upload_id") or ""
        staged = mrpack.get(upload_id)
        if staged is None:
            raise PendingModpackError(
                "The uploaded modpack is no longer available — upload the "
                ".mrpack again and install it from the server's dashboard"
            )
        result = client.install_mrpack_archive(
            staged.path,
            install_path,
            loader=intent.get("loader") or staged.summary.get("loader"),
            clean_install=False,
            allow_missing=True,
            mod_side_overrides=intent.get("mod_side_overrides"),
            progress_callback=progress_callback,
        )
        result.setdefault("name", staged.filename)
        result["_source"] = "upload"
        result["_filename"] = staged.filename
        result["_upload_id"] = upload_id
        return result

    project_id = intent.get("project_id") or ""
    if not project_id:
        raise PendingModpackError("The stored modpack request names no project")

    result = client.install_modpack(
        project_id=project_id,
        install_path=install_path,
        mc_version=intent.get("mc_version") or None,
        loader=intent.get("loader") or None,
        clean_install=False,
        allow_missing=True,
        mod_side_overrides=intent.get("mod_side_overrides"),
        progress_callback=progress_callback,
    )
    result["_source"] = "project"
    return result


def modpack_record(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build the ``modpack`` block to persist on the server record."""
    record = {
        "projectId": result.get("project_id"),
        "versionId": result.get("version_id"),
        "name": result.get("name"),
        "version": result.get("version"),
        "mcVersion": result.get("mc_version"),
        "loaders": result.get("loaders", []),
        "installedAt": iso_z_now(),
    }
    if result.get("_source") == "upload":
        record["source"] = "upload"
        record["fileName"] = result.get("_filename")

    # Warnings the install could not resolve on its own. Nobody was watching
    # when they were raised, so they are kept on the record for the dashboard
    # to show once the user is back.
    uncertain = result.get("uncertain_mod_files") or []
    if uncertain:
        record["uncertainMods"] = uncertain
    missing = result.get("missing_files") or []
    if missing:
        record["missingFiles"] = missing
    return record


def cleanup(result: Dict[str, Any]) -> None:
    """Release anything the install consumed. Best effort, never raises."""
    if result.get("_source") == "upload" and result.get("_upload_id"):
        try:
            mrpack.discard(result["_upload_id"])
        except Exception:  # noqa: BLE001 - cleanup must not fail an install
            logger.warning("could not discard staged pack %s", result["_upload_id"])
