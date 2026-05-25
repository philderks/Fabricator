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
 * Start the playit agent (no-op if already running).
 * @returns {Promise<{ ok: boolean }>}
 */
export function startPlayit() {
  return post('/api/playit/start')
}

/**
 * Stop the playit agent.
 * @returns {Promise<{ ok: boolean }>}
 */
export function stopPlayit() {
  return post('/api/playit/stop')
}
