/**
 * playit.gg Tunnel Store (setup syntax).
 *
 * Single source of truth for the playit tunnel — both the Server Overview
 * onboarding panel and the Settings → Network row consume from here. There
 * is exactly ONE poller across the whole app: callers ref-count it via
 * usePolling()/stopPolling(), so the interval runs while ≥1 consumer is
 * active and stops the moment the last one unmounts.
 *
 * Response shape (matches backend.playit.routes):
 *   { status, address, claim_url, error_reason, binary_verified }
 *
 * `status` values:
 *   stopped | claiming | starting | running | needs_tunnel | connected
 *                                                              | error | unsupported
 *
 * Semantics:
 *   running       — daemon healthy, address not (yet) known. Neutral, NOT an error.
 *   needs_tunnel  — daemon healthy, but no tunnel allocated. Actionable, NOT an error.
 *   connected     — rundata confirmed tunnel + display_address.
 *   error         — REAL failure (disabled_reason, daemon stdout match, daemon crash).
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getPlayitStatus, startPlayit, stopPlayit, resetPlayit } from '../api/playit'

const POLL_MS = 3000

export const usePlayitStore = defineStore('playit', () => {
  // ---------- State ----------
  const status         = ref('stopped')
  const address        = ref(null)
  const claimUrl       = ref(null)
  const errorReason    = ref(null)
  const binaryVerified = ref(true)

  // Internal — not returned. Ref-counted poller and a debounce so two
  // consumers mounting in the same tick don't trigger two parallel fetches.
  const _consumers     = ref(0)
  const _pollHandle    = ref(null)
  const _inFlightFetch = ref(null)

  // ---------- Getters ----------
  // `isActive` is the truthy-toggle predicate: the daemon is live (or being
  // brought up). Includes the neutral states `running` and `needs_tunnel`
  // — the user shouldn't see the toggle flip off just because we don't
  // have an address yet.

  const isActive    = computed(() =>
    ['claiming', 'starting', 'running', 'needs_tunnel', 'connected'].includes(status.value)
  )
  const isConnected = computed(() =>
    status.value === 'connected' && address.value !== null
  )
  const isClaiming    = computed(() => status.value === 'claiming')
  const isRunning     = computed(() => status.value === 'running')
  const isNeedsTunnel = computed(() => status.value === 'needs_tunnel')
  const isError       = computed(() => status.value === 'error')
  const isUnsupported = computed(() => status.value === 'unsupported')

  // ---------- Internals ----------

  function _applySnapshot(data) {
    status.value         = data?.status ?? 'stopped'
    address.value        = data?.address      ?? null
    claimUrl.value       = data?.claim_url    ?? null
    errorReason.value    = data?.error_reason ?? null
    // binary_verified defaults to true so the absence of the field in older
    // backends (none, but defense-in-depth) doesn't flash the warning.
    binaryVerified.value = data?.binary_verified !== false
  }

  // ---------- Actions ----------

  async function fetch() {
    if (_inFlightFetch.value) return _inFlightFetch.value
    const promise = (async () => {
      try {
        _applySnapshot(await getPlayitStatus())
      } catch {
        // Network hiccup — keep stale state. Don't flash an absent card.
      } finally {
        _inFlightFetch.value = null
      }
    })()
    _inFlightFetch.value = promise
    return promise
  }

  async function start() {
    try {
      _applySnapshot(await startPlayit())
    } catch (err) {
      // True transport failure — surface a generic error so the UI can react.
      status.value = 'error'
      errorReason.value = err?.message || 'Network error'
    }
  }

  async function stop() {
    try {
      _applySnapshot(await stopPlayit())
    } catch (err) {
      status.value = 'error'
      errorReason.value = err?.message || 'Network error'
    }
  }

  async function reset() {
    try {
      _applySnapshot(await resetPlayit())
    } catch (err) {
      status.value = 'error'
      errorReason.value = err?.message || 'Network error'
    }
  }

  /**
   * Subscribe to polling. Returns an unsubscribe function — every component
   * that subscribes must also unsubscribe (typically in onUnmounted) or the
   * poller leaks past the consumer's lifetime.
   */
  function subscribe() {
    _consumers.value += 1
    if (_consumers.value === 1) {
      // Fire an immediate fetch so the new consumer doesn't have to wait
      // a full POLL_MS for first paint.
      fetch()
      _pollHandle.value = setInterval(fetch, POLL_MS)
    }
    let released = false
    return function unsubscribe() {
      if (released) return
      released = true
      _consumers.value -= 1
      if (_consumers.value <= 0) {
        _consumers.value = 0
        if (_pollHandle.value) {
          clearInterval(_pollHandle.value)
          _pollHandle.value = null
        }
      }
    }
  }

  return {
    // state
    status, address, claimUrl, errorReason, binaryVerified,
    // getters
    isActive, isConnected, isClaiming, isRunning, isNeedsTunnel, isError, isUnsupported,
    // actions
    fetch, start, stop, reset, subscribe,
  }
})
