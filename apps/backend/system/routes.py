"""System-level routes (self-update and diagnostics)."""
import os

from flask import Blueprint, jsonify, request

from backend.system.update_service import update_service


system_bp = Blueprint('system', __name__, url_prefix='/api/system')


def _self_update_disabled() -> bool:
    """True when this deployment manages updates out-of-band.

    The container image sets ``FABRICATOR_DISABLE_SELF_UPDATE=1`` to turn the
    in-app self-updater into a no-op — updates then arrive by pulling a new
    image tag instead of running the curl|bash installer in-process. Gating the
    endpoint is also the compensating control for the container case: the panel
    has no auth, so an exposed unauthenticated ``POST /update`` would otherwise
    be a remote curl|bash trigger.
    """
    return os.environ.get('FABRICATOR_DISABLE_SELF_UPDATE') == '1'


@system_bp.route('/update/status', methods=['GET'])
def get_update_status():
    """Expose current updater state and latest-version check."""
    status = update_service.get_status()
    status['selfUpdateDisabled'] = _self_update_disabled()
    return jsonify(status)


@system_bp.route('/update', methods=['POST'])
def trigger_update():
    """Start an asynchronous self-update job."""
    if _self_update_disabled():
        return jsonify({
            'started': False,
            'selfUpdateDisabled': True,
            'error': (
                'In-app updates are disabled in this deployment. This instance '
                'runs as a container image — update by pulling a new tag: '
                'docker compose pull && docker compose up -d.'
            ),
        }), 403
    payload = request.get_json(silent=True) or {}
    requested_version = payload.get('version')
    result = update_service.trigger_update(requested_version)
    status = 202 if result.get('started') else 409
    return jsonify(result), status
