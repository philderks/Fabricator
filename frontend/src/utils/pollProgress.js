/**
 * Retry policy for install-progress polling.
 *
 * The install runs in a backend worker thread; polling `GET /install/progress`
 * only *observes* it. That asymmetry is the whole point of this module: a failed
 * poll says nothing about the install, so treating one as a failed install is
 * simply wrong. Both pollers used to do exactly that — a single blip (Wi-Fi
 * drop, the panel briefly busy, a proxy hiccup) aborted the watch and told the
 * user the installation had failed while it carried on to a successful finish.
 *
 * So a transient failure is retried, and when we do give up we report *lost
 * contact*, never failure — the caller cannot know which it was, and claiming
 * the stronger thing is what made the old behaviour a bug.
 */

/** Cadence shared by both pollers (the create modal set the precedent). */
export const POLL_INTERVAL_MS = 750

/**
 * Consecutive failures tolerated before giving up — about 6 seconds at the
 * cadence above. Long enough to ride out a blip or a quick backend restart,
 * short enough that a genuinely dead panel doesn't spin forever.
 */
export const MAX_CONSECUTIVE_FAILURES = 8

/**
 * Whether a poll error is worth retrying.
 *
 * `ApiError` carries `status` 0 for network/transport failures and the real
 * HTTP status otherwise. A 4xx means the panel answered and gave a definite
 * "no" (404: the server record is gone) — retrying that just delays the
 * inevitable. 5xx, 429 and transport failures are all plausibly momentary.
 *
 * An `AbortError` is a deliberate cancellation, never a fault to retry.
 */
export function isRetryablePollError(error) {
  if (error?.name === 'AbortError') return false

  const status = error?.status
  if (status === 0 || status === undefined || status === null) return true
  if (status === 429) return true
  return status >= 500
}

/**
 * Wrap a progress fetch with consecutive-failure tolerance.
 *
 * Returns a function whose result is one of:
 *   `{ status: 'ok', progress }`          — use it
 *   `{ status: 'retry', error, failures }` — transient, poll again
 *   `{ status: 'giveup', error }`          — stop watching; say contact was lost
 *
 * The failure count resets on every success, so an install that blips
 * repeatedly over a long run is never penalised for its total blip count —
 * only for going dark continuously.
 *
 * @param {() => Promise<object>} fetchProgress
 * @param {{maxFailures?: number}} [options]
 */
export function createProgressPoller(fetchProgress, options = {}) {
  const maxFailures = options.maxFailures ?? MAX_CONSECUTIVE_FAILURES
  let failures = 0

  return async function poll() {
    try {
      const progress = await fetchProgress()
      failures = 0
      return { status: 'ok', progress }
    } catch (error) {
      if (!isRetryablePollError(error)) {
        return { status: 'giveup', error }
      }
      failures += 1
      if (failures >= maxFailures) {
        return { status: 'giveup', error }
      }
      return { status: 'retry', error, failures }
    }
  }
}

/**
 * The message shown when polling gives up. Deliberately does not claim the
 * install failed — it very likely did not.
 */
export const LOST_CONTACT_MESSAGE =
  'Lost contact with the panel while installing. The install is most likely ' +
  'still running in the background — reopen the server to check on it.'
