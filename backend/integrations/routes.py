"""MCP integration management: the on/off switch + API-token CRUD.

All four routes are session-gated by the global auth gate (none are in the
public or setup allowlists) and are bucketed NEVER for API tokens — a token can
never manage tokens or flip the switch. Secrets appear in exactly one response:
the 201 body of a token mint; every other response is metadata only.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.auth import service

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")


@integrations_bp.route("/mcp", methods=["GET"])
def get_mcp():
    """Return the switch state and token metadata (read from the file, no secret)."""
    return jsonify(
        {"enabled": service.mcp_state()["enabled"], "tokens": service.list_tokens()}
    )


@integrations_bp.route("/mcp", methods=["PUT"])
def set_mcp():
    """Flip the on/off switch. Turning it off leaves tokens intact (inert)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("enabled"), bool):
        return jsonify({"error": "enabled (boolean) is required"}), 400
    service.set_mcp_enabled(data["enabled"])
    return jsonify({"enabled": data["enabled"]}), 200


@integrations_bp.route("/mcp/tokens", methods=["POST"])
def create_mcp_token():
    """Mint a token. Allowed regardless of switch state (an off switch just makes
    it inert). The returned ``token`` is the only time the secret is shown."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400
    try:
        created = service.create_token(data.get("name"), data.get("scope"))
    except service.TokenLimitReached as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(created), 201


@integrations_bp.route("/mcp/tokens/<token_id>", methods=["DELETE"])
def delete_mcp_token(token_id):
    """Revoke a token by id — takes effect live (the gate reads fresh)."""
    if not service.revoke_token(token_id):
        return jsonify({"error": "token not found"}), 404
    return "", 204
