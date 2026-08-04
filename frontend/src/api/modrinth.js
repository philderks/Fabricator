/**
 * Modrinth API Client
 * Handles all Modrinth-related API requests
 */

import { get, post, del, ApiError } from './client'


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
 * @param {string} [options.version_id] - Install this exact version instead of
 *   letting the backend resolve the newest compatible one (#56). Recorded as a
 *   pin, so it is distinguishable from an auto-resolved install.
 * @param {string} [options.replaces] - Filename of the jar this supersedes;
 *   removed only after the new one is safely on disk. Must be a bare filename
 *   inside the mods folder. This is what makes a version *change* rather than
 *   a second copy.
 * @returns {Promise<Object>} `{ success, file, path, versionId, versionNumber, replaced }`
 */
export async function installMod(modId, { mc_version, loader, server_id, version_id, replaces }) {
  const body = { mc_version, loader, server_id }
  if (version_id) body.version_id = version_id
  if (replaces) body.replaces = replaces
  return post(`/api/modrinth/mod/${modId}/install`, body)
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
 * Identify every jar in a server's mods folder by content hash.
 *
 * One request for the whole folder. The backend hashes the jars and asks
 * Modrinth's bulk `version_files` endpoint, so this replaces the old
 * per-filename slug guessing that issued ~3.6 requests per jar and tripped
 * Modrinth's rate limit on any hand-populated modpack (#52).
 *
 * @param {string|number} serverId - Server identifier
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<{resolved: Record<string, {projectId:string, slug:string|null, title:string|null, iconUrl:string|null, versionId:string|null, versionNumber:string|null}>}>}
 *   Jars Modrinth doesn't recognise are absent from `resolved`.
 */
export async function resolveInstalledMods(serverId, options = {}) {
  return get(
    `/api/modrinth/servers/${encodeURIComponent(serverId)}/resolve-installed`,
    {},
    { signal: options.signal }
  )
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

/**
 * Upload a .mrpack exported from the Modrinth app (#53).
 *
 * The archive is staged, not installed: the response describes what the pack
 * declares (`name`, `minecraft_version`, `loader`, ...) so the create form can
 * fill itself in before the target server exists. Install it later with
 * `installUploadedModpack(upload_id, ...)`.
 *
 * Uses XMLHttpRequest rather than fetch for the one thing fetch cannot give
 * us: upload progress events. Same shape as `uploadWorld` in api/backups.js.
 *
 * @param {File} file
 * @param {object} [opts]
 * @param {(pct:number)=>void} [opts.onProgress] 0–100, or -1 when indeterminate
 * @param {(abort:()=>void)=>void} [opts.registerAbort] receives a cancel fn
 * @returns {Promise<Object>} staged pack summary including `upload_id`
 */
export function uploadModpackArchive(file, { onProgress, registerAbort } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/modrinth/modpack/upload?filename=${encodeURIComponent(file.name)}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')

    if (typeof registerAbort === 'function') {
      registerAbort(() => xhr.abort())
    }

    xhr.upload.onprogress = (event) => {
      if (typeof onProgress !== 'function') return
      onProgress(event.lengthComputable ? Math.round((event.loaded / event.total) * 100) : -1)
    }

    xhr.onload = () => {
      let data = {}
      try {
        data = JSON.parse(xhr.responseText || '{}')
      } catch (_) {
        data = {}
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data)
      } else {
        reject(new ApiError(
          data.error || data.message || `Upload failed with status ${xhr.status}`,
          xhr.status,
          data && Object.keys(data).length ? data : null
        ))
      }
    }

    xhr.onerror = () => reject(new ApiError('Network error during upload', 0, null))
    xhr.onabort = () => reject(new ApiError('Upload cancelled', 0, null))

    xhr.send(file)
  })
}

/**
 * Install a previously uploaded .mrpack onto a server.
 *
 * `force` acknowledges a pack built for a different Minecraft version or
 * loader than the server runs; without it the backend answers 409 with the
 * mismatch spelled out. The upload survives a failed install so the
 * missing-files / uncertain-mod-side retries can reuse it.
 *
 * @param {string} uploadId
 * @param {Object} options
 * @returns {Promise<Object>} Installation result
 */
export async function installUploadedModpack(uploadId, {
  server_id,
  loader,
  clean_install = false,
  create_backup = false,
  allow_missing = false,
  mod_side_overrides = null,
  force = false
}) {
  return post(`/api/modrinth/modpack/upload/${encodeURIComponent(uploadId)}/install`, {
    server_id,
    loader,
    clean_install,
    create_backup,
    allow_missing,
    mod_side_overrides,
    force
  })
}

/** Drop a staged .mrpack the user decided not to install. */
export async function discardModpackUpload(uploadId) {
  return del(`/api/modrinth/modpack/upload/${encodeURIComponent(uploadId)}`)
}
