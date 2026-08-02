/**
 * playit.gg Agent API
 * Thin wrappers around the four playit control endpoints. All four return the
 * same daemon-level snapshot shape:
 *   { status, claim_url, error_reason, binary_trust, tunnels, tunnels_known }
 */

import { get, post } from './client'

/**
 * Fetch the current agent state.
 * @returns {Promise<{status:string, claim_url:string|null, error_reason:string|null, binary_trust:'verified'|'unverified'|'system'|'missing', tunnels:Array<object>, tunnels_known:boolean}>}
 */
export function getPlayitStatus() {
  return get('/api/playit/status')
}

/**
 * Start the playit agent (no-op if already running). The response body is the
 * same snapshot shape as getPlayitStatus(); caller branches on `status`.
 */
export function startPlayit() {
  return post('/api/playit/start')
}

/**
 * Stop the playit agent. Same snapshot shape as getPlayitStatus().
 */
export function stopPlayit() {
  return post('/api/playit/stop')
}

/**
 * Reset playit — stop the daemon and delete the persisted secret, forcing a
 * fresh claim on the next start. Same snapshot shape as getPlayitStatus().
 */
export function resetPlayit() {
  return post('/api/playit/reset')
}
