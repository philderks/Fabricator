/**
 * Modrinth primary files usually save as `{slug}-{…}.jar`. Some uploads use a
 * “compact” basename without hyphens (e.g. slug `server-side-horror` → `serversidehorror-….jar`).
 */

function jarNameMatchesModrinthProjectId(jarName, projectIdOrSlug) {
  const n = (jarName || '').toLowerCase()
  const id = String(projectIdOrSlug || '').toLowerCase()
  if (!n.endsWith('.jar') || id.length < 2) return false
  if (n === `${id}.jar` || n.startsWith(`${id}-`) || n.startsWith(`${id}_`)) {
    return true
  }
  const idCompact = id.replace(/[-_]/g, '')
  if (idCompact.length < 2) return false
  const nFlat = n.replace(/_/g, '')
  return nFlat === `${idCompact}.jar` || nFlat.startsWith(`${idCompact}-`)
}

/**
 * @param {string} jarName
 * @param {{ id?: string, slug?: string } | null} projectRef - Modrinth project id and/or slug
 */
export function installedJarMatchesProjectRef(jarName, projectRef) {
  if (!projectRef) return false
  const ids = [...new Set(
    [projectRef.slug, projectRef.id].filter(Boolean).map((s) => String(s).toLowerCase())
  )]
  return ids.some((id) => jarNameMatchesModrinthProjectId(jarName, id))
}

export function installedJarMatchesBrowseHit(jarName, mod) {
  if (!mod) return false
  return installedJarMatchesProjectRef(jarName, {
    id: mod.project_id,
    slug: mod.slug
  })
}

/**
 * Does an installed entry correspond to a Modrinth project?
 *
 * Prefers the install manifest (`entry.modrinth`), which records the project
 * id at install time and is therefore exact. Only jars with no manifest entry
 * — dropped into the folder by hand, or installed before the manifest existed
 * — fall back to guessing from the filename, which misses whenever the jar
 * isn't named after its project (`voicechat-bukkit-2.6.20.jar` for
 * `simple-voice-chat`).
 *
 * @param {{ modrinth?: { projectId?: string, slug?: string } | null, filename?: string, name?: string }} entry
 * @param {{ id?: string, slug?: string } | null} projectRef
 */
export function installedEntryMatchesProjectRef(entry, projectRef) {
  if (!entry || !projectRef) return false

  const recorded = entry.modrinth
  if (recorded && (recorded.projectId || recorded.slug)) {
    const wanted = [projectRef.id, projectRef.slug]
      .filter(Boolean).map((s) => String(s).toLowerCase())
    const owned = [recorded.projectId, recorded.slug]
      .filter(Boolean).map((s) => String(s).toLowerCase())
    return owned.some((id) => wanted.includes(id))
  }

  return installedJarMatchesProjectRef(entry.filename || entry.name, projectRef)
}

/**
 * Manifest-aware variant of {@link installedJarMatchesBrowseHit}, taking a
 * Modrinth search hit (`project_id` + `slug`) instead of a project ref.
 *
 * @param {object} entry - installed entry
 * @param {{ project_id?: string, slug?: string } | null} mod - Modrinth search hit
 */
export function installedEntryMatchesBrowseHit(entry, mod) {
  if (!mod) return false
  return installedEntryMatchesProjectRef(entry, { id: mod.project_id, slug: mod.slug })
}
