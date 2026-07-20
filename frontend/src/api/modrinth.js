/**
 * Modrinth API Client
 * Handles all Modrinth-related API requests
 */

import { get, post } from './client'


/**
 * Search for mods on Modrinth
 * @param {Object} params - Search parameters
 * @param {string} params.query - Search query
 * @param {string} params.version - Minecraft version (e.g., '1.21.3')
 * @param {string} params.loader - Mod loader (e.g., 'fabric', 'forge')
 * @param {string} params.sort - Sort order (relevance, downloads, updated, newest)
 * @param {number} params.limit - Number of results (default: 20)
 * @param {number} params.offset - Pagination offset (default: 0)
 * @returns {Promise<Object>} Search results with hits array
 */
export async function searchMods({
  query = '',
  version = '',
  loader = '',
  projectType = 'mod',
  sort = 'relevance',
  limit = 20,
  offset = 0
}, options = {}) {
  return get('/api/modrinth/search', {
    query,
    mc_version: version,
    loader,
    project_type: projectType,
    index: sort,
    limit,
    offset
  }, { signal: options.signal })
}

/**
 * Get detailed information about a specific mod
 * @param {string} modId - Modrinth mod ID or slug
 * @returns {Promise<Object>} Mod details
 */
export async function getModDetails(modId, options = {}) {
  return get(`/api/modrinth/mod/${modId}`, {}, { signal: options.signal })
}

/**
 * Get available versions for a mod
 * @param {string} modId - Modrinth mod ID
 * @param {Object} filters - Version filters
 * @param {string} filters.game_version - Minecraft version
 * @param {string} filters.loader - Mod loader
 * @returns {Promise<Array>} List of available versions
 */
export async function getModVersions(modId, filters = {}, options = {}) {
  return get(`/api/modrinth/mod/${modId}/versions`, filters, { signal: options.signal })
}

/**
 * Install a mod on the server
 * @param {string} modId - Modrinth mod ID
 * @param {Object} options - Installation options
 * @param {string} options.mc_version - Minecraft version
 * @param {string} options.loader - Mod loader
 * @param {string|number} options.server_id - Target server identifier
 * @returns {Promise<Object>} Installation result
 */
export async function installMod(modId, { mc_version, loader, server_id }) {
  return post(`/api/modrinth/mod/${modId}/install`, {
    mc_version,
    loader,
    server_id
  })
}

/**
 * Get list of available mod categories
 * @returns {Promise<Array>} List of categories
 */
export async function getCategories() {
  return get('/api/modrinth/categories')
}

/**
 * Get list of available mod loaders
 * @returns {Promise<Array>} List of loaders (fabric, forge, quilt, etc.)
 */
export async function getLoaders() {
  return get('/api/modrinth/loaders')
}

/**
 * Get list of available Minecraft game versions
 * @returns {Promise<Array>} List of game versions
 */
export async function getGameVersions() {
  return get('/api/modrinth/game-versions')
}

/**
 * Search for modpacks on Modrinth.
 * @param {Object} params - Search parameters
 * @param {string} params.query - Search query
 * @param {string} params.version - Minecraft version
 * @param {string} params.loader - Mod loader (fabric, quilt, etc.)
 * @param {string} params.sort - Sort order
 * @param {number} params.limit - Number of results
 * @param {number} params.offset - Pagination offset
 * @returns {Promise<Object>} Search results with hits array
 */
export async function searchModpacks({
  query = '',
  version = '',
  loader = '',
  sort = 'relevance',
  limit = 8,
  offset = 0
}) {
  return get('/api/modrinth/modpacks/search', {
    query,
    mc_version: version,
    loader,
    index: sort,
    limit: Math.min(limit, 50),
    offset
  })
}

/**
 * Fetch details for a Modrinth project by slug or ID.
 * @param {string} projectIdOrSlug - Modrinth project identifier
 * @returns {Promise<Object>} Project details
 */
export async function getProjectDetails(projectIdOrSlug) {
  return get(`/api/modrinth/project/${encodeURIComponent(projectIdOrSlug)}`)
}

/**
 * Resolve a project version compatible with the requested game version/loader.
 * @param {string} projectId - Modrinth project ID or slug
 * @param {Object} options - Resolve options
 * @param {string} options.mc_version - Minecraft version
 * @param {string} options.loader - Loader (fabric, quilt, etc.)
 * @param {string[]} [options.loaders] - Accepted loader facet chain (plugin
 *   servers); when provided it supersedes `loader` server-side.
 * @returns {Promise<Object>} Resolved version payload
 */
export async function resolveProjectVersion(projectId, { mc_version, loader, loaders }) {
  const params = { mc_version }
  if (Array.isArray(loaders) && loaders.length) {
    params.loaders = loaders.join(',')
  } else if (loader) {
    params.loader = loader
  }
  return get(`/api/modrinth/project/${encodeURIComponent(projectId)}/resolve-version`, params)
}

/**
 * Poll modpack install progress for a server.
 * @param {string|number} serverId - Server identifier
 * @returns {Promise<Object>} Progress info with active, stage, current, total, detail
 */
export async function getModpackInstallProgress(serverId) {
  return get(`/api/modrinth/modpack/install-progress/${encodeURIComponent(serverId)}`)
}

/**
 * Install a modpack on a server.
 * Downloads the .mrpack, installs all server-side mods, and applies overrides.
 * @param {string} projectId - Modrinth project ID or slug
 * @param {Object} options - Installation options
 * @param {string} options.mc_version - Minecraft version
 * @param {string} options.loader - Mod loader
 * @param {string|number} options.server_id - Target server identifier
 * @returns {Promise<Object>} Installation result
 */
export async function installModpack(projectId, {
  mc_version,
  loader,
  server_id,
  clean_install = false,
  create_backup = false,
  allow_missing = false,
  mod_side_overrides = null
}) {
  return post(`/api/modrinth/modpack/${encodeURIComponent(projectId)}/install`, {
    mc_version,
    loader,
    server_id,
    clean_install,
    create_backup,
    allow_missing,
    mod_side_overrides
  })
}
