/**
 * playit.gg Agent API
 *
 * Thin wrappers around the four playit control endpoints. All four answer the
 * same daemon-level snapshot, so callers branch on `status` whichever they
 * called:
 *   { status, claim_url, error_reason, binary_trust, tunnels, tunnels_known }
 */

import { get, post } from './client'

export function getPlayitStatus() {
  return get('/api/playit/status')
}

/** No-op if the agent is already running. */
export function startPlayit() {
  return post('/api/playit/start')
}

export function stopPlayit() {
  return post('/api/playit/stop')
}

/** Stop the daemon and delete the persisted secret, forcing a fresh claim. */
export function resetPlayit() {
  return post('/api/playit/reset')
}
