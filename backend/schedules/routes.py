"""Flask routes for scheduled commands (``/api/servers/<id>/schedules``)."""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

from backend.schedules import service
from backend.utils.routes import require_server


schedules_bp = Blueprint("schedules", __name__, url_prefix="/api")


@schedules_bp.route("/servers/<server_id>/schedules", methods=["GET"])
@require_server
def list_schedules(server_id, server):
    return jsonify(service.list_schedules(server))


@schedules_bp.route("/servers/<server_id>/schedules", methods=["POST"])
@require_server
def create_schedule(server_id, server):
    clean, error = service.validate(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(service.create_schedule(server_id, clean)), 201


@schedules_bp.route("/servers/<server_id>/schedules/<schedule_id>", methods=["PUT"])
@require_server
def update_schedule(server_id, server, schedule_id):
    clean, error = service.validate(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    schedule = service.update_schedule(server_id, schedule_id, clean)
    if schedule is None:
        return jsonify({"error": "Schedule not found"}), 404
    return jsonify(schedule)


@schedules_bp.route("/servers/<server_id>/schedules/<schedule_id>", methods=["DELETE"])
@require_server
def delete_schedule(server_id, server, schedule_id):
    if not service.delete_schedule(server_id, schedule_id):
        return jsonify({"error": "Schedule not found"}), 404
    return jsonify({"success": True})


@schedules_bp.route("/servers/<server_id>/schedules/<schedule_id>/run", methods=["POST"])
@require_server
def run_schedule_now(server_id, server, schedule_id):
    if service.get_schedule(server_id, schedule_id) is None:
        return jsonify({"error": "Schedule not found"}), 404
    threading.Thread(
        target=service.run_schedule, args=(server_id, schedule_id), daemon=True
    ).start()
    return jsonify({"success": True}), 202
