import { resolveInstalledMods } from '../api/modrinth'

/**
 * @typedef {{ displayTitle: string, iconUrl: string | null, projectId: string, slug: string | null }} ResolvedMeta
 */

/** @type {Map<string, ResolvedMeta>} */
const resolvedMetaByFilename = new Map()

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
    // A hash match knows exactly which release the jar is, so a jar dropped in
    // by hand stops reporting "local" (#56 — the reporter's stated workaround
    // was doing exactly that, and the panel then disagreed with reality).
    version: meta.versionNumber || mod.version,
    modrinthGuess: meta.projectId
      ? {
          projectId: meta.projectId,
          slug: meta.slug,
          versionId: meta.versionId || null,
          versionNumber: meta.versionNumber || null
        }
      : null
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
    // Rate limited or offline. The page still works, just with fewer icons.
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
      slug: meta.slug || null,
      // Exact, because it came from the file's hash rather than its name.
      versionId: meta.versionId || null,
      versionNumber: meta.versionNumber || null
    })
  }
  return byFilename
}

/**
 * Resolve `displayTitle` and `iconUrl` for each mod entry (for .jar files).
 * Returns a NEW list — does not mutate `mods` in place.
 *
 * Resolution order per jar: install manifest (already on the entry) → content
 * hash (one bulk request for the folder). Nothing else: unrecognised jars keep
 * their filename (#81).
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

  // Exact identification by content hash, one request for the folder.
  const byHash = await _resolveByHash(options.serverId, signal)
  if (signal?.aborted) return result

  // A hash miss means Modrinth doesn't have this exact file (hand-added,
  // repackaged or never published there), so the jar keeps its filename.
  // Guessing slugs from the name instead cost a 404 per jar on every page
  // load (#81). The backend caches misses, so re-asking next load is free.
  for (const entry of pending) {
    const meta = byHash.get(entry.key)
    if (!meta) continue
    resolvedMetaByFilename.set(entry.key, meta)
    result[entry.idx] = _withMeta(entry.mod, meta)
  }

  return result
}
