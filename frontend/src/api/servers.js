/**
 * Server Management API Client
 * Handles all server-related API requests
 */

import { get, post, put, del } from './client'

/**
 * Get server status
 * @returns {Promise<Object>} Server status information
 */
export async function getServerStatus() {
  return get('/api/status')
}

/**
 * Get list of all servers
 * @returns {Promise<Array>} List of servers
 */
export async function getServers() {
  return get('/api/servers')
}

/**
 * Get details for a specific server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Server details
 */
export async function getServer(serverId) {
  return get(`/api/servers/${serverId}`)
}

/**
 * Create a new server
 * @param {Object} serverData - Server configuration
 * @param {string} serverData.name - Server name
 * @param {string} serverData.version - Minecraft version
 * @param {string} serverData.loader - Mod loader (fabric, forge, etc.)
 * @param {number} serverData.port - Server port
 * @param {number} serverData.maxPlayers - Max players
 * @param {string} serverData.difficulty - Difficulty level
 * @param {string} serverData.gamemode - Default gamemode
 * @param {number} serverData.memory - Memory allocation in GB
 * @returns {Promise<Object>} Created server details
 */
export async function createServer(serverData) {
  return post('/api/servers', serverData)
}

/**
 * Update server settings
 * @param {string|number} serverId - Server ID
 * @param {Object} settings - Server settings to update
 * @returns {Promise<Object>} Updated server details
 */
export async function updateServerSettings(serverId, settings) {
  return put(`/api/servers/${serverId}/settings`, settings)
}

/**
 * Delete a server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Deletion confirmation
 */
export async function deleteServer(serverId) {
  return del(`/api/servers/${serverId}`)
}

/**
 * Start a server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Server start result
 */
export async function startServer(serverId) {
  return post(`/api/servers/${serverId}/start`)
}

/**
 * Stop a server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Server stop result
 */
export async function stopServer(serverId) {
  return post(`/api/servers/${serverId}/stop`)
}

/**
 * Restart a server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Server restart result
 */
export async function restartServer(serverId) {
  return post(`/api/servers/${serverId}/restart`)
}

/**
 * Browse server files
 * @param {string|number} serverId - Server ID
 * @param {Object} params - Query params
 * @param {string} params.path - Relative path inside the server directory
 * @returns {Promise<Object>} Current path and directory entries
 */
export async function browseServerFiles(serverId, params = {}) {
  return get(`/api/servers/${serverId}/files`, params)
}

/**
 * Fetch a text file's contents
 * @param {string|number} serverId - Server ID
 * @param {string} path - Relative file path
 * @returns {Promise<Object>} File content payload
 */
export async function getServerFile(serverId, path) {
  return get(`/api/servers/${serverId}/files/content`, { path })
}

/**
 * Save a text file's contents
 * @param {string|number} serverId - Server ID
 * @param {string} path - Relative file path
 * @param {string} content - File contents
 * @returns {Promise<Object>} Save result
 */
export async function saveServerFile(serverId, path, content) {
  return put(`/api/servers/${serverId}/files/content`, { path, content })
}

/**
 * Get server console logs
 * @param {string|number} serverId - Server ID
 * @param {Object} options - Log options
 * @param {number} options.limit - Number of log lines to retrieve
 * @param {number} options.offset - Offset for pagination
 * @returns {Promise<Object>} Server logs
 */
export async function getServerLogs(serverId, { limit = 100, offset = 0 } = {}) {
  return get(`/api/servers/${serverId}/logs`, { limit, offset })
}

/**
 * Send command to server console
 * @param {string|number} serverId - Server ID
 * @param {string} command - Console command to execute
 * @returns {Promise<Object>} Command execution result
 */
export async function sendServerCommand(serverId, command) {
  return post(`/api/servers/${serverId}/console`, { command })
}

/**
 * Get list of installed mods for a server
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Array>} List of installed mods
 */
export async function getInstalledMods(serverId) {
  return get(`/api/servers/${serverId}/mods`)
}

/**
 * Remove a mod from the server
 * @param {string|number} serverId - Server ID
 * @param {string} modName - Mod name or filename
 * @returns {Promise<Object>} Removal result
 */
export async function removeMod(serverId, modName) {
  return del(`/api/servers/${serverId}/mods/${encodeURIComponent(modName)}`)
}

/**
 * Create a server backup
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Backup creation result
 */
export async function createBackup(serverId) {
  return post(`/api/servers/${serverId}/backup`)
}

/**
 * Get list of server backups
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Array>} List of backups
 */
export async function getBackups(serverId) {
  return get(`/api/servers/${serverId}/backups`)
}

/**
 * Restore server from backup
 * @param {string|number} serverId - Server ID
 * @param {string} backupId - Backup ID
 * @returns {Promise<Object>} Restore result
 */
export async function restoreBackup(serverId, backupId) {
  return post(`/api/servers/${serverId}/backups/${backupId}/restore`)
}

/**
 * Get server performance metrics
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Performance metrics (CPU, RAM, TPS, etc.)
 */
export async function getServerMetrics(serverId) {
  return get(`/api/servers/${serverId}/metrics`)
}

/**
 * Install a server (download files, write configs)
 * @param {string|number} serverId - Server ID
 * @returns {Promise<Object>} Installation result
 */
export async function installServer(serverId) {
  return post(`/api/servers/${serverId}/install`)
}

/**
 * Get Fabric-supported Minecraft versions
 * @returns {Promise<Array>} List of game versions from Fabric Meta
 */
export async function getFabricGameVersions() {
  return get('/api/fabric/versions/game')
}

/**
 * Get Fabric loader versions for a Minecraft version
 * @param {string} mcVersion - Minecraft version filter
 * @returns {Promise<Array>} Loader versions metadata
 */
export async function getFabricLoaderVersions(mcVersion) {
  const params = mcVersion ? { mc_version: mcVersion } : {}
  return get('/api/fabric/versions/loader', params)
}

/**
 * Get overall system metrics (CPU, memory)
 * @returns {Promise<Object>} System metrics payload
 */
export async function getSystemMetrics() {
  return get('/api/metrics/system')
}
