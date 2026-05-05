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

export function installedJarMatchesBrowseHit(jarName, mod) {
  if (!mod) return false
  const ids = [...new Set(
    [mod.slug, mod.project_id].filter(Boolean).map((s) => String(s).toLowerCase())
  )]
  return ids.some((id) => jarNameMatchesModrinthProjectId(jarName, id))
}
