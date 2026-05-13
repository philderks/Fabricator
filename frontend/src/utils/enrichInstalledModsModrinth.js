import { getModDetails } from '../api/modrinth'
import { pLimit, withBackoff } from '../api/throttle'
import { installedJarMatchesProjectRef } from './modrinthJarMatch'

/**
 * @typedef {{ displayTitle: string, iconUrl: string | null }} ResolvedMeta
 */

/** @type {Map<string, ResolvedMeta | null>} */
const resolvedMetaByFilename = new Map()

// Module-scoped limiter — shared across all enrichment runs so overlapping
// invocations (e.g. multiple navigations) cooperatively share the budget.
const limiter = pLimit(4)

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
 * Map a Modrinth-style jar basename to project title + icon using the same
 * slug / id rules as `installedJarMatchesProjectRef`.
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
  for (let i = parts.length; i >= 1; i -= 1) {
    if (signal?.aborted) return null
    const candidate = parts.slice(0, i).join('-')
    if (!candidate) continue
    try {
      const d = await withBackoff(
        () => getModDetails(candidate, { signal }),
        { signal, retries: 2 }
      )
      const ref = { id: d.id, slug: d.slug }
      if (!installedJarMatchesProjectRef(filename, ref)) continue
      return {
        displayTitle: d.title || d.slug || candidate,
        iconUrl: d.icon_url || null
      }
    } catch (error) {
      if (error?.name === 'AbortError') return null
      // 404 or network — try shorter slug prefix
    }
  }
  return null
}

/**
 * Resolve `displayTitle` and `iconUrl` for each mod entry (for .jar files).
 * Returns a NEW list — does not mutate `mods` in place.
 *
 * @param {Array<{ name?: string, filename?: string, displayTitle?: string | null, iconUrl?: string | null }>} mods
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<Array<object>>}
 */
export async function enrichInstalledModsWithModrinth(mods, options = {}) {
  if (!Array.isArray(mods) || mods.length === 0) return []
  const signal = options.signal

  // Build the result list up-front; jar entries get filled in as resolutions
  // settle. Non-jar entries pass through unchanged (with cloned object).
  const result = mods.map((m) => ({ ...m }))

  const tasks = result.map((mod, idx) => {
    const filename = mod?.filename || mod?.name
    if (!filename || !filename.toLowerCase().endsWith('.jar')) {
      return null
    }
    const key = filename.toLowerCase()

    // Cache fast-path: short-circuit network entirely.
    if (resolvedMetaByFilename.has(key)) {
      const cached = resolvedMetaByFilename.get(key)
      if (cached) {
        result[idx] = { ...mod, displayTitle: cached.displayTitle, iconUrl: cached.iconUrl }
      }
      return null
    }

    return limiter(
      async () => {
        if (signal?.aborted) return
        try {
          const meta = await resolveJarFilenameToModrinthMeta(filename, { signal })
          // Don't poison cache with aborted resolutions.
          if (signal?.aborted) return
          resolvedMetaByFilename.set(key, meta)
          if (meta) {
            result[idx] = { ...mod, displayTitle: meta.displayTitle, iconUrl: meta.iconUrl }
          }
        } catch (error) {
          if (error?.name === 'AbortError') return
          resolvedMetaByFilename.set(key, null)
        }
      },
      { signal }
    ).catch((error) => {
      // Swallow AbortError from the limiter — other tasks may still resolve.
      if (error?.name !== 'AbortError') throw error
    })
  }).filter(Boolean)

  await Promise.allSettled(tasks)
  return result
}
