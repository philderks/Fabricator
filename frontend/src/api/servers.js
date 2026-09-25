/**
 * Server Management API Client
 *
 * One function per panel route. Anything whose name, arguments and URL say all
 * there is to say carries no comment — a doc block that restates the signature
 * is one more thing to keep in sync and tells a reader nothing. Comments below
 * are reserved for behaviour you cannot read off the call itself.
 */

import { get, post, put, del, ApiError } from './client'

export async function getServers() {
  return get('/api/servers')
}

export async function getServer(serverId) {
  return get(`/api/servers/${serverId}`)
}

export async function createServer(serverData) {
  return post('/api/servers', serverData)
}

export async function updateServerSettings(serverId, settings) {
  return put(`/api/servers/${serverId}/settings`, settings)
}

/** @param {('always'|'never'|'last')} mode */
export async function setServerAutoStart(serverId, mode) {
  return put(`/api/servers/${serverId}/autostart`, { mode })
}

export async function deleteServer(serverId) {
  return del(`/api/servers/${serverId}`)
}

export async function startServer(serverId) {
  return post(`/api/servers/${serverId}/start`)
}

export async function stopServer(serverId) {
  return post(`/api/servers/${serverId}/stop`)
}

export async function restartServer(serverId) {
  return post(`/api/servers/${serverId}/restart`)
}

export async function browseServerFiles(serverId, params = {}) {
  return get(`/api/servers/${serverId}/files`, params)
}

/** @param {{q: string, path?: string, limit?: number}} params - `q` matches names case-insensitively */
export async function searchServerFiles(serverId, params = {}) {
  return get(`/api/servers/${serverId}/files/search`, params)
}

export async function getServerFile(serverId, path) {
  return get(`/api/servers/${serverId}/files/content`, { path })
}

export async function saveServerFile(serverId, path, content) {
  return put(`/api/servers/${serverId}/files/content`, { path, content })
}

/**
 * Upload one file into a directory under the server's install path.
 *
 * The raw File is the request body (not multipart) to match the backend's
 * streamed, size-capped upload routes. Callers upload one file per call and
 * fan out over a multi-select themselves, which is what keeps per-file
 * progress and per-file failure reporting possible.
 *
 * Uses XMLHttpRequest rather than fetch for the one thing fetch still can't
 * do: upload progress events. Same shape as `uploadWorld` in ./backups.js.
 *
 * @param {string} dirPath - Relative destination folder ('' for the root)
 * @param {object} [opts]
 * @param {boolean} [opts.overwrite] - Replace an existing file of that name
 * @param {(pct:number)=>void} [opts.onProgress] 0-100, or -1 when indeterminate
 * @param {(abort:()=>void)=>void} [opts.registerAbort] receives a cancel fn
 */
export function uploadServerFile(serverId, dirPath, file, { overwrite = false, onProgress, registerAbort } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    // encodeURIComponent matters more than it looks: a bare '+' in a query
    // string decodes to a space, which would rename every Fabric jar on the
    // way in (fabric-api-0.102.0+1.21.jar -> fabric-api-0.102.0 1.21.jar).
    const params = new URLSearchParams({ path: dirPath || '', filename: file.name })
    if (overwrite) params.set('overwrite', 'true')

    xhr.open('POST', `/api/servers/${serverId}/files/upload?${params.toString()}`)
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
 * Delete one or more entries under the server's install path.
 *
 * Always answers 200 with `{ success, deleted, errors }` so a partial failure
 * in a multi-select reports per entry rather than sinking the batch. A
 * non-empty folder comes back in `errors` with `code: 'not-empty'` unless
 * `recursive` is set.
 */
export async function deleteServerFiles(serverId, paths, { recursive = false } = {}) {
  return del(`/api/servers/${serverId}/files`, { paths, recursive })
}

export async function createServerFolder(serverId, dirPath, name) {
  return post(`/api/servers/${serverId}/files/folder`, { path: dirPath || '', name })
}

export async function getServerLogs(serverId, { limit = 1000 } = {}) {
  return get(`/api/servers/${serverId}/logs`, { limit })
}

export async function sendServerCommand(serverId, command) {
  return post(`/api/servers/${serverId}/console`, { command })
}

export async function getInstalledMods(serverId) {
  return get(`/api/servers/${serverId}/mods`)
}

export async function removeMod(serverId, modName) {
  return del(`/api/servers/${serverId}/mods/${encodeURIComponent(modName)}`)
}

/** Bulk sibling of removeMod; answers with `{ deleted, errors }` per filename. */
export async function bulkRemoveMods(serverId, filenames) {
  return del(`/api/servers/${serverId}/mods`, { filenames })
}

export async function getServerMetrics(serverId) {
  return get(`/api/servers/${serverId}/metrics`)
}

export async function installServer(serverId, { modpack = null } = {}) {
  // A modpack passed here is installed by the same backend worker that
  // installs the loader, so closing the screen or refreshing no longer loses
  // it (#63). Omit it and the install is loader-only, as before.
  return post(`/api/servers/${serverId}/install`, modpack ? { modpack } : {})
}

export async function getServerInstallProgress(serverId) {
  return get(`/api/servers/${encodeURIComponent(serverId)}/install/progress`)
}

/**
 * Take a mandatory snapshot, then upgrade a Vanilla or Paper server release.
 * `version` must be newer than the current one. Poll the returned job through
 * getServerInstallProgress().
 */
export async function upgradeServer(serverId, version) {
  return post(`/api/servers/${encodeURIComponent(serverId)}/upgrade`, { version })
}

export async function getLoaderGameVersions(loader) {
  return get(`/api/loaders/${encodeURIComponent(loader)}/versions/game`)
}

/** Loader-native version metadata; the entry shape varies by loader. */
export async function getLoaderVersions(loader, mcVersion) {
  const params = mcVersion ? { mc_version: mcVersion } : {}
  return get(`/api/loaders/${encodeURIComponent(loader)}/versions/loader`, params)
}

export async function getSystemMetrics() {
  return get('/api/metrics/system')
}

/** @param {{mcVersion?: string, requiredJava?: number, javaPath?: string}} options */
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

/** Starts an async install; poll the returned `task_id` with getJavaInstallProgress(). */
export async function installJava(major) {
  return post('/api/java/install', { major })
}

export async function getJavaInstallProgress(taskId) {
  return get(`/api/java/install/progress/${taskId}`)
}

/** `{ managed: Array<{major, path, version}>, system: {path, version, installed} }` */
export async function getInstalledJava() {
  return get('/api/java/installed')
}

export async function uninstallJava(major) {
  return del(`/api/java/installed/${major}`)
}

export async function getUpdateStatus() {
  return get('/api/system/update/status')
}

export async function triggerUpdate(version = 'latest') {
  return post('/api/system/update', { version })
}
