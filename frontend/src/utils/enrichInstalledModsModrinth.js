import { getModDetails } from '../api/modrinth'
import { installedJarMatchesProjectRef } from './modrinthJarMatch'

/** @type {Map<string, { displayTitle: string, iconUrl: string | null } | null>} */
const resolvedMetaByFilename = new Map()

/**
 * Map a Modrinth-style jar basename to project title + icon using the same
 * slug / id rules as `installedJarMatchesProjectRef`.
 *
 * @param {string} filename
 * @returns {Promise<{ displayTitle: string, iconUrl: string | null } | null>}
 */
export async function resolveJarFilenameToModrinthMeta(filename) {
  if (!filename || !filename.toLowerCase().endsWith('.jar')) return null
  const stem = filename.slice(0, -4)
  const parts = stem.split('-')
  for (let i = parts.length; i >= 1; i -= 1) {
    const candidate = parts.slice(0, i).join('-')
    if (!candidate) continue
    try {
      const d = await getModDetails(candidate)
      const ref = { id: d.id, slug: d.slug }
      if (!installedJarMatchesProjectRef(filename, ref)) continue
      return {
        displayTitle: d.title || d.slug || candidate,
        iconUrl: d.icon_url || null
      }
    } catch {
      // 404 or network — try shorter slug prefix
    }
  }
  return null
}

/**
 * Fills `displayTitle` and `iconUrl` on each mod entry (for .jar files).
 * Runs in the background with limited concurrency; safe to call without await.
 *
 * @param {Array<{ name?: string, filename?: string, displayTitle?: string | null, iconUrl?: string | null }>} mods
 * @param {{ concurrency?: number }} [options]
 */
export async function enrichInstalledModsWithModrinth(mods, options = {}) {
  const concurrency = Math.max(1, options.concurrency ?? 4)
  if (!Array.isArray(mods) || mods.length === 0) return

  const jarMods = mods.filter((m) => {
    const fn = m?.filename || m?.name
    return fn && fn.toLowerCase().endsWith('.jar')
  })
  if (jarMods.length === 0) return

  let cursor = 0
  async function worker() {
    for (;;) {
      const i = cursor++
      if (i >= jarMods.length) return
      const mod = jarMods[i]
      const filename = mod.filename || mod.name
      if (!filename) continue

      const cached = resolvedMetaByFilename.get(filename)
      if (cached !== undefined) {
        if (cached) {
          mod.displayTitle = cached.displayTitle
          mod.iconUrl = cached.iconUrl
        }
        continue
      }

      try {
        const meta = await resolveJarFilenameToModrinthMeta(filename)
        resolvedMetaByFilename.set(filename, meta)
        if (meta) {
          mod.displayTitle = meta.displayTitle
          mod.iconUrl = meta.iconUrl
        }
      } catch {
        resolvedMetaByFilename.set(filename, null)
      }
    }
  }

  const n = Math.min(concurrency, jarMods.length)
  await Promise.all(Array.from({ length: n }, () => worker()))
}
