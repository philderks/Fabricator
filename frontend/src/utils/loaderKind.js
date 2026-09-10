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
// Loaders with no add-on surface at all — only these hide the add-on tab.
const NO_CONTENT_LOADERS = new Set(['vanilla'])

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
/**
 * True when a Modrinth category name is a loader rather than a content tag.
 *
 * Modrinth tags loader compatibility as ordinary categories, mixed in with
 * things like 'adventure' or 'optimization', so a project's `categories` array
 * has to be filtered before it can be read as "which loaders does this run on".
 * @param {string} category
 * @returns {boolean}
 */
export function isLoaderCategory(category) {
  const key = String(category || '').trim().toLowerCase()
  return MOD_LOADERS.has(key) || PLUGIN_LOADERS.has(key)
}

export function loaderContentKind(loader) {
  const key = String(loader || '').trim().toLowerCase()
  if (PLUGIN_LOADERS.has(key)) return 'plugin'
  if (NO_CONTENT_LOADERS.has(key)) return 'none'
  // Mod loaders AND any unrecognised loader fall through to 'mod' so the add-on
  // tab fails open (shown as "Mods") instead of vanishing for a loader that
  // isn't in this list — mirrors the backend's loader_content_kind default.
  return 'mod'
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
