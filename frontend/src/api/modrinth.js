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
  sort = 'relevance',
  limit = 20,
  offset = 0 
}) {
  return get('/api/modrinth/search', {
    query,
    mc_version: version,
    loader,
    index: sort,
    limit,
    offset
  })
}

/**
 * Get detailed information about a specific mod
 * @param {string} modId - Modrinth mod ID or slug
 * @returns {Promise<Object>} Mod details
 */
export async function getModDetails(modId) {
  return get(`/api/modrinth/mod/${modId}`)
}

/**
 * Get available versions for a mod
 * @param {string} modId - Modrinth mod ID
 * @param {Object} filters - Version filters
 * @param {string} filters.game_version - Minecraft version
 * @param {string} filters.loader - Mod loader
 * @returns {Promise<Array>} List of available versions
 */
export async function getModVersions(modId, filters = {}) {
  return get(`/api/modrinth/mod/${modId}/versions`, filters)
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
