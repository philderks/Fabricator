"""HTTP endpoints for the playit.gg agent.

Frontend consumes the response body — `start` and `stop` return the full
post-action status so the toggle handler can branch on `status` and
`error_reason` without an extra poll.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from backend.managed import is_managed

from . import agent

playit_bp = Blueprint("playit", __name__, url_prefix="/api/playit")

_MANAGED_403 = ({"error": "playit is disabled in managed mode"}, 403)


@playit_bp.route("/status", methods=["GET"])
def status():
    return jsonify(agent.get_status())


@playit_bp.route("/start", methods=["POST"])
def start():
    if is_managed():
        body, code = _MANAGED_403
        return jsonify(body), code
    agent.start()
    return jsonify(agent.get_status())


@playit_bp.route("/stop", methods=["POST"])
def stop():
    agent.stop()
    return jsonify(agent.get_status())


@playit_bp.route("/reset", methods=["POST"])
def reset():
    if is_managed():
        body, code = _MANAGED_403
        return jsonify(body), code
    agent.reset()
    return jsonify(agent.get_status())
