/** Human-friendly label for an installed mod row (mirrors Modrinth search titles). */
export function installedModDisplayName(mod) {
  if (!mod) return ''
  if (mod.displayTitle) return mod.displayTitle
  const n = mod.name || mod.filename || ''
  return n.replace(/\.jar$/i, '')
}

/** Single-letter placeholder when no project icon is available */
export function installedModInitial(mod) {
  const label = installedModDisplayName(mod)
  if (!label) return '?'
  const c = label.replace(/[^a-zA-Z0-9]/g, '').slice(0, 1)
  return c ? c.toUpperCase() : '?'
}
