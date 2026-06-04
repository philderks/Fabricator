/**
 * playit.gg Agent API
 * Thin wrappers around the three playit control endpoints.
 */

import { get, post } from './client'

/**
 * Fetch the current agent state.
 * @returns {Promise<{ status: string, address: string|null, claim_url: string|null }>}
 */
export function getPlayitStatus() {
  return get('/api/playit/status')
}

/**
 * Start the playit agent (no-op if already running). The response body is
 * the same shape as getPlayitStatus() — caller branches on `status`.
 * @returns {Promise<{ status, address, claim_url, error_reason, binary_verified }>}
 */
export function startPlayit() {
  return post('/api/playit/start')
}

/**
 * Stop the playit agent.
 * @returns {Promise<{ status, address, claim_url, error_reason, binary_verified }>}
 */
export function stopPlayit() {
  return post('/api/playit/stop')
}

/**
 * Reset playit — stop the daemon and delete the persisted secret, forcing a
 * fresh claim on the next start.
 * @returns {Promise<{ status, address, claim_url, error_reason, binary_verified }>}
 */
export function resetPlayit() {
  return post('/api/playit/reset')
}
