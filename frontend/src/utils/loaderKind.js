/**
 * Loader → add-on-content classification (frontend mirror of the backend
 * installer `content_kind`).
 *
 * Bukkit-family loaders (Paper/Purpur/Folia/Pufferfish) consume *plugins*
 * (installed into `plugins/`); the classic mod loaders consume *mods*
 * (`mods/`); Vanilla has no add-on surface at all. The backend is the source
 * of truth for where jars actually land — this helper only drives UI labels
 * and which browse `project_type` the modal requests.
 */

const PLUGIN_LOADERS = new Set(['paper', 'purpur', 'folia', 'pufferfish'])
const MOD_LOADERS = new Set(['fabric', 'quilt', 'forge', 'neoforge'])

// Modrinth loader-category compatibility chains for plugin platforms — mirror
// of the backend installers' `modrinth_loader_facets`. A Paper server runs
// paper/spigot/bukkit-tagged plugins; Folia stays strict.
const PLUGIN_FACETS = {
  paper: ['paper', 'spigot', 'bukkit'],
  purpur: ['purpur', 'paper', 'spigot', 'bukkit'],
  folia: ['folia'],
  pufferfish: ['paper', 'spigot', 'bukkit']
}

/**
 * Modrinth loader facets accepted for a server's add-ons.
 * Plugin platforms return their compatibility chain; mod loaders return
 * `[loader]`; Vanilla returns `[]`.
 * @param {string} loader
 * @returns {string[]}
 */
export function loaderModrinthFacets(loader) {
  const key = String(loader || '').trim().toLowerCase()
  if (PLUGIN_FACETS[key]) return [...PLUGIN_FACETS[key]]
  if (MOD_LOADERS.has(key)) return [key]
  return []
}

/**
 * @param {string} loader
 * @returns {'plugin'|'mod'|'none'}
 */
export function loaderContentKind(loader) {
  const key = String(loader || '').trim().toLowerCase()
  if (PLUGIN_LOADERS.has(key)) return 'plugin'
  if (MOD_LOADERS.has(key)) return 'mod'
  return 'none'
}

/** True for Paper/Purpur/Folia/Pufferfish. */
export function isPluginLoader(loader) {
  return loaderContentKind(loader) === 'plugin'
}

/**
 * Modrinth `project_type` to browse for this loader.
 * @returns {'plugin'|'mod'}
 */
export function loaderProjectType(loader) {
  return loaderContentKind(loader) === 'plugin' ? 'plugin' : 'mod'
}

/**
 * User-facing noun for this loader's add-on content.
 * @param {string} loader
 * @param {boolean} plural
 */
export function contentLabel(loader, plural = true) {
  const kind = loaderContentKind(loader)
  if (kind === 'plugin') return plural ? 'Plugins' : 'Plugin'
  return plural ? 'Mods' : 'Mod'
}
