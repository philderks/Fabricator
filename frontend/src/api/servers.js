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
 * Remove multiple mods from the server in one request
 * @param {string|number} serverId - Server ID
 * @param {string[]} filenames - Array of mod filenames to remove
 * @returns {Promise<Object>} Bulk removal result with deleted/errors arrays
 */
export async function bulkRemoveMods(serverId, filenames) {
  return del(`/api/servers/${serverId}/mods`, { filenames })
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
 * Delete a server backup
 * @param {string|number} serverId - Server ID
 * @param {string} backupId - Backup ID (filename without .zip)
 * @returns {Promise<Object>} Deletion result
 */
export async function deleteBackup(serverId, backupId) {
  return del(`/api/servers/${serverId}/backups/${backupId}`)
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
 * Get Minecraft versions supported by a loader.
 * @param {string} loader - Loader name (e.g. 'fabric', 'vanilla')
 * @returns {Promise<Array<{version: string, stable: boolean, type?: string}>>}
 */
export async function getLoaderGameVersions(loader) {
  return get(`/api/loaders/${encodeURIComponent(loader)}/versions/game`)
}

/**
 * Get loader-specific versions for a Minecraft version.
 * @param {string} loader - Loader name
 * @param {string} [mcVersion] - Minecraft version filter
 * @returns {Promise<Array>} Loader-native version metadata (shape varies by loader)
 */
export async function getLoaderVersions(loader, mcVersion) {
  const params = mcVersion ? { mc_version: mcVersion } : {}
  return get(`/api/loaders/${encodeURIComponent(loader)}/versions/loader`, params)
}

/**
 * Get overall system metrics (CPU, memory)
 * @returns {Promise<Object>} System metrics payload
 */
export async function getSystemMetrics() {
  return get('/api/metrics/system')
}

/**
 * Get Java installation status and platform download URL
 * @param {Object} options
 * @param {string} options.mcVersion - Optional Minecraft version to resolve required Java.
 * @param {number} options.requiredJava - Optional forced required Java version.
 * @param {string} options.javaPath - Optional java executable/path to check.
 * @returns {Promise<Object>} Java runtime and recommendation payload
 */
export async function getJavaStatus(options = {}) {
  const params = {}
  if (options.mcVersion) {
    params.mc_version = options.mcVersion
  }
  if (options.requiredJava) {
    params.required_java = options.requiredJava
  }
  if (options.javaPath) {
    params.java_path = options.javaPath
  }
  return get('/api/java/status', params)
}

/**
 * Start a managed Java install for the given major version.
 * @param {number} major - Java major version to install (e.g. 21)
 * @returns {Promise<Object>} Task descriptor including task_id
 */
export async function installJava(major) {
  return post('/api/java/install', { major })
}

/**
 * Poll a managed Java install task for progress.
 * @param {string} taskId - Task id returned by installJava()
 * @returns {Promise<Object>} Current task status and bytes-downloaded
 */
export async function getJavaInstallProgress(taskId) {
  return get(`/api/java/install/progress/${taskId}`)
}

/**
 * Get Fabricator self-update status.
 * @returns {Promise<Object>} Update state and latest-version information
 */
export async function getUpdateStatus() {
  return get('/api/system/update/status')
}

/**
 * Trigger Fabricator self-update.
 * @param {string} version - Optional target version (default latest)
 * @returns {Promise<Object>} Update start result
 */
export async function triggerUpdate(version = 'latest') {
  return post('/api/system/update', { version })
}
