/**
 * Single source of truth for the server-status display logic.
 *
 * The backend's runtime registry only knows "running" or "stopped" — for
 * in-flight states owned by a route handler (pending, installing, starting,
 * stopping, failed) the persisted status is authoritative and must NOT be
 * overwritten by the registry's default "stopped".
 *
 * Cross-Branch contract (CC5)
 * --------------------------
 * RUNTIME_KNOWN_STATUSES below MUST mirror the backend's
 * `_RUNTIME_KNOWN_STATUSES` set in `backend/server/routes.py`. The backend
 * pin is enforced by `tests/test_runtime_status_pin.py`; when that test
 * fails, this file is the corresponding frontend update. Keep the two
 * lockstep — drift here will silently render in-flight states as the
 * registry's "stopped" default.
 */

export const RUNTIME_KNOWN_STATUSES = new Set(['running', 'stopped'])

/**
 * Resolve a server's effective display status.
 *
 * @param {Object} server - Server object with optional `status` (persisted)
 *   and `runtime.status` (registry-side) fields.
 * @param {string} [fallback='pending'] - Returned when neither field yields
 *   a meaningful value. 'pending' (the default) matches the persisted
 *   initial state of a freshly-created server; older callers may pass
 *   'unknown' for backward-compat but new call sites should accept the
 *   'pending' default.
 * @returns {string}
 */
export function getEffectiveStatus(server, fallback = 'pending') {
  const persisted = server?.status
  const runtime = server?.runtime?.status
  if (persisted && !RUNTIME_KNOWN_STATUSES.has(persisted)) {
    return persisted
  }
  return runtime || persisted || fallback
}
