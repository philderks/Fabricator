"""System-level routes (self-update and diagnostics)."""
from flask import Blueprint, jsonify, request

from backend.system.update_service import update_service


system_bp = Blueprint('system', __name__, url_prefix='/api/system')


@system_bp.route('/update/status', methods=['GET'])
def get_update_status():
    """Expose current updater state and latest-version check."""
    return jsonify(update_service.get_status())


@system_bp.route('/update', methods=['POST'])
def trigger_update():
    """Start an asynchronous self-update job."""
    payload = request.get_json(silent=True) or {}
    requested_version = payload.get('version')
    result = update_service.trigger_update(requested_version)
    status = 202 if result.get('started') else 409
    return jsonify(result), status
