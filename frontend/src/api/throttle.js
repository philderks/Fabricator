/**
 * Lightweight throttle / retry primitives.
 *
 * `pLimit(concurrency)` returns a FIFO-fair limiter; `withBackoff(producer)`
 * retries a thunk with capped exponential backoff + Retry-After awareness.
 *
 * Both honor an optional `AbortSignal`. The limiter never calls
 * `producer()` after an abort; producers own their own cancellation
 * (they receive `signal` from the caller and pass it to `fetch`).
 */

function makeAbortError(message = 'Aborted') {
  // Prefer DOMException so `error.name === 'AbortError'` matches whatwg-fetch.
  if (typeof DOMException !== 'undefined') {
    return new DOMException(message, 'AbortError')
  }
  const err = new Error(message)
  err.name = 'AbortError'
  return err
}

/**
 * Returns a limiter function. Each `limiter(producer)` call dispatches the
 * producer thunk when a slot is available. Slots are FIFO. Returns a
 * `Promise` of the producer's resolved value (or rejection).
 *
 * Per-call options:
 *   - `signal` (AbortSignal): if pre-aborted, producer never runs and the
 *     promise rejects with AbortError. If aborted while queued, the entry
 *     is spliced from the queue and rejects with AbortError. If aborted
 *     while running, the limiter does NOT cancel the producer — producers
 *     own cancellation via their own signal forwarding.
 *
 * Limiter object exposes:
 *   - `limiter.activeCount()` — running tasks.
 *   - `limiter.pendingCount()` — queued tasks.
 *   - `limiter.clearQueue()` — reject all pending (not yet started) with
 *     AbortError; running tasks finish.
 *
 * @param {number} concurrency
 */
export function pLimit(concurrency) {
  const cap = Math.max(1, Math.floor(concurrency) || 1)
  let active = 0
  const queue = []

  function next() {
    while (active < cap && queue.length > 0) {
      const entry = queue.shift()
      if (entry.cancelled) continue
      // detach signal listener — entry has left the queue
      if (entry.signal && entry.abortHandler) {
        entry.signal.removeEventListener('abort', entry.abortHandler)
      }
      active += 1
      Promise.resolve()
        .then(() => entry.producer())
        .then(
          (value) => {
            active -= 1
            entry.resolve(value)
            next()
          },
          (error) => {
            active -= 1
            entry.reject(error)
            next()
          }
        )
    }
  }

  function limiter(producer, options = {}) {
    const signal = options.signal
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(makeAbortError())
        return
      }

      const entry = { producer, resolve, reject, signal, abortHandler: null, cancelled: false }

      if (signal) {
        entry.abortHandler = () => {
          // If still queued (not yet started), splice + reject.
          const idx = queue.indexOf(entry)
          if (idx !== -1) {
            entry.cancelled = true
            queue.splice(idx, 1)
            if (entry.abortHandler) {
              signal.removeEventListener('abort', entry.abortHandler)
            }
            reject(makeAbortError())
          }
          // If running: we don't cancel the producer — its own signal does.
        }
        signal.addEventListener('abort', entry.abortHandler)
      }

      queue.push(entry)
      next()
    })
  }

  limiter.activeCount = () => active
  limiter.pendingCount = () => queue.length
  limiter.clearQueue = () => {
    const pending = queue.splice(0, queue.length)
    for (const entry of pending) {
      entry.cancelled = true
      if (entry.signal && entry.abortHandler) {
        entry.signal.removeEventListener('abort', entry.abortHandler)
      }
      entry.reject(makeAbortError())
    }
  }

  return limiter
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(makeAbortError())
      return
    }
    let timer = null
    const onAbort = () => {
      if (timer !== null) clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
      reject(makeAbortError())
    }
    timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal?.addEventListener('abort', onAbort)
  })
}

function defaultIsRetryable(error) {
  if (!error) return false
  if (error.name === 'AbortError') return false
  const status = error.status
  return status === 429 || status === 503 || status === 0
}

function readRetryAfterMs(error) {
  const retryAfter = error?.data?.retry_after
  if (typeof retryAfter !== 'number' || !Number.isFinite(retryAfter) || retryAfter < 0) {
    return null
  }
  return Math.round(retryAfter * 1000)
}

/**
 * Retry `producer` on retryable errors with capped exponential backoff +
 * Retry-After awareness.
 *
 * @param {() => Promise<any>} producer
 * @param {Object} [options]
 * @param {number} [options.retries=3]
 * @param {number} [options.baseDelayMs=500]
 * @param {number} [options.maxDelayMs=8000]
 * @param {AbortSignal} [options.signal]
 * @param {(error:any)=>boolean} [options.isRetryable]
 */
export async function withBackoff(producer, options = {}) {
  const retries = options.retries ?? 3
  const baseDelayMs = options.baseDelayMs ?? 500
  const maxDelayMs = options.maxDelayMs ?? 8000
  const signal = options.signal
  const isRetryable = options.isRetryable ?? defaultIsRetryable

  let attempt = 0
  // attempts = retries + 1 total tries
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (signal?.aborted) throw makeAbortError()
    try {
      return await producer()
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      if (attempt >= retries || !isRetryable(error)) throw error

      // Compute delay: Retry-After (seconds) wins; else exponential w/ jitter.
      const retryAfterMs = readRetryAfterMs(error)
      let delay
      if (retryAfterMs !== null) {
        delay = Math.min(retryAfterMs, maxDelayMs)
      } else {
        const exp = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt)
        const jitter = Math.random() * exp * 0.25
        delay = exp + jitter
      }
      attempt += 1
      await sleep(delay, signal)
    }
  }
}
