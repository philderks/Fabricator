import { getModDetails, resolveInstalledMods } from '../api/modrinth'
import { pLimit, withBackoff } from '../api/throttle'
import { installedJarMatchesProjectRef } from './modrinthJarMatch'

/**
 * @typedef {{ displayTitle: string, iconUrl: string | null, projectId: string, slug: string | null }} ResolvedMeta
 */

/** @type {Map<string, ResolvedMeta | null>} */
const resolvedMetaByFilename = new Map()

// Module-scoped limiter — shared across all enrichment runs so overlapping
// invocations (e.g. multiple navigations) cooperatively share the budget.
const limiter = pLimit(4)

// Ceiling on filename-guessed lookups per enrichment run. The hash lookup
// identifies everything Modrinth actually knows about, so anything reaching the
// fallback is a jar that was repackaged, renamed or never published there —
// a long tail that is not worth spending the API budget on. Without this cap a
// folder of unrecognised jars reproduces the original fan-out (#52).
const MAX_FALLBACK_LOOKUPS = 20

// Prefix candidates tried per jar in the fallback, shortest first. A Modrinth
// slug is nearly always the leading segment(s) of the filename, so two attempts
// cover the realistic cases; the old unbounded longest-first walk spent one
// request per hyphen-separated segment and 404'd through almost all of them.
const MAX_PREFIX_CANDIDATES = 2

/**
 * Drop a single filename (or the whole cache) from the resolved metadata
 * cache. Called from store mutation paths so deleted/replaced jars don't
 * keep stale metadata after re-listing.
 *
 * @param {string} [filename] - normalized lower-case; if omitted clears all.
 */
export function invalidateModrinthMetaCache(filename) {
  if (filename === undefined || filename === null) {
    resolvedMetaByFilename.clear()
    return
  }
  if (typeof filename !== 'string') return
  resolvedMetaByFilename.delete(filename.toLowerCase())
}

/**
 * Map a Modrinth-style jar basename to project title + icon by guessing the
 * project slug from the filename.
 *
 * Fallback only — `enrichInstalledModsWithModrinth` resolves by content hash
 * first, which is exact. This is for jars the hash lookup didn't recognise, so
 * it is deliberately bounded to the shortest few prefixes rather than walking
 * every one.
 *
 * @param {string} filename
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<ResolvedMeta | null>}
 */
export async function resolveJarFilenameToModrinthMeta(filename, options = {}) {
  if (!filename || !filename.toLowerCase().endsWith('.jar')) return null
  const signal = options.signal
  const stem = filename.slice(0, -4)
  const parts = stem.split('-')

  const candidates = []
  for (let i = 1; i <= parts.length && candidates.length < MAX_PREFIX_CANDIDATES; i += 1) {
    const candidate = parts.slice(0, i).join('-')
    if (candidate) candidates.push(candidate)
  }

  for (const candidate of candidates) {
    if (signal?.aborted) return null
    try {
      const d = await withBackoff(
        () => getModDetails(candidate, { signal }),
        { signal, retries: 2 }
      )
      const ref = { id: d.id, slug: d.slug }
      if (!installedJarMatchesProjectRef(filename, ref)) continue
      return {
        displayTitle: d.title || d.slug || candidate,
        iconUrl: d.icon_url || null,
        // Kept so the caller can link to the project page. The match was
        // verified above, but it's still filename-derived — callers surface it
        // as `modrinthGuess`, never as the install manifest.
        projectId: d.id,
        slug: d.slug || null
      }
    } catch (error) {
      if (error?.name === 'AbortError') return null
      // 404 or network — try the next candidate
    }
  }
  return null
}

/**
 * Merge resolved metadata onto a mod entry, without mutating it.
 *
 * The project ref lands in `modrinthGuess`, kept distinct from `modrinth` (the
 * backend's install manifest) so an inference is never mistaken for a record
 * of where the jar actually came from.
 *
 * @param {object} mod
 * @param {ResolvedMeta} meta
 */
function _withMeta(mod, meta) {
  return {
    ...mod,
    displayTitle: meta.displayTitle,
    iconUrl: meta.iconUrl,
    modrinthGuess: meta.projectId ? { projectId: meta.projectId, slug: meta.slug } : null
  }
}

/**
 * Ask the backend to identify the whole mods folder by file hash.
 *
 * @returns {Promise<Map<string, ResolvedMeta>>} keyed by lower-case filename;
 *   empty when the lookup is unavailable (offline, rate limited, no serverId).
 */
async function _resolveByHash(serverId, signal) {
  const byFilename = new Map()
  if (serverId === undefined || serverId === null || serverId === '') return byFilename

  let payload
  try {
    payload = await resolveInstalledMods(serverId, { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    // Rate limited or offline. Degrade to the filename fallback rather than
    // rendering nothing — the page still works, just with fewer icons.
    return byFilename
  }

  const resolved = payload?.resolved
  if (!resolved || typeof resolved !== 'object') return byFilename

  for (const [filename, meta] of Object.entries(resolved)) {
    if (!meta) continue
    byFilename.set(filename.toLowerCase(), {
      displayTitle: meta.title || meta.slug || filename,
      iconUrl: meta.iconUrl || null,
      projectId: meta.projectId || null,
      slug: meta.slug || null
    })
  }
  return byFilename
}

/**
 * Resolve `displayTitle` and `iconUrl` for each mod entry (for .jar files).
 * Returns a NEW list — does not mutate `mods` in place.
 *
 * Resolution order per jar: install manifest (already on the entry) → content
 * hash (one bulk request for the folder) → bounded filename guess.
 *
 * @param {Array<{ name?: string, filename?: string, displayTitle?: string | null, iconUrl?: string | null }>} mods
 * @param {{ signal?: AbortSignal, serverId?: string | number }} [options]
 * @returns {Promise<Array<object>>}
 */
export async function enrichInstalledModsWithModrinth(mods, options = {}) {
  if (!Array.isArray(mods) || mods.length === 0) return []
  const signal = options.signal

  // Build the result list up-front; jar entries get filled in as resolutions
  // settle. Non-jar entries pass through unchanged (with cloned object).
  const result = mods.map((m) => ({ ...m }))

  // Everything that still needs identifying: a jar, with no manifest-provided
  // title, and not already in the per-session cache.
  const pending = []
  result.forEach((mod, idx) => {
    const filename = mod?.filename || mod?.name
    if (!filename || !filename.toLowerCase().endsWith('.jar')) return
    // Already identified by the install manifest — no guessing, no network.
    if (mod.displayTitle) return

    const key = filename.toLowerCase()
    // Cache fast-path: short-circuit network entirely.
    if (resolvedMetaByFilename.has(key)) {
      const cached = resolvedMetaByFilename.get(key)
      if (cached) result[idx] = _withMeta(mod, cached)
      return
    }
    pending.push({ idx, mod, filename, key })
  })

  if (pending.length === 0) return result

  // Pass 1 — exact identification by content hash, one request for the folder.
  const byHash = await _resolveByHash(options.serverId, signal)
  if (signal?.aborted) return result

  const unresolved = []
  for (const entry of pending) {
    const meta = byHash.get(entry.key)
    if (meta) {
      resolvedMetaByFilename.set(entry.key, meta)
      result[entry.idx] = _withMeta(entry.mod, meta)
    } else {
      unresolved.push(entry)
    }
  }

  // Pass 2 — bounded filename guessing for the leftovers only.
  const tasks = unresolved.slice(0, MAX_FALLBACK_LOOKUPS).map((entry) =>
    limiter(
      async () => {
        if (signal?.aborted) return
        try {
          const meta = await resolveJarFilenameToModrinthMeta(entry.filename, { signal })
          // Don't poison cache with aborted resolutions.
          if (signal?.aborted) return
          resolvedMetaByFilename.set(entry.key, meta)
          if (meta) {
            result[entry.idx] = _withMeta(entry.mod, meta)
          }
        } catch (error) {
          if (error?.name === 'AbortError') return
          resolvedMetaByFilename.set(entry.key, null)
        }
      },
      { signal }
    ).catch((error) => {
      // Swallow AbortError from the limiter — other tasks may still resolve.
      if (error?.name !== 'AbortError') throw error
    })
  )

  await Promise.allSettled(tasks)
  return result
}
