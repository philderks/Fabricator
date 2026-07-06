/**
 * Backup Manager API Client
 *
 * Wraps the per-server backup endpoints exposed by backend/backups/routes.py.
 * Job-progress polling (`getBackupJob`) is keyed on a globally-unique job id
 * returned by the `run` and `restore` endpoints — no server scoping needed.
 */

import { get, post, put, del, ApiError } from './client'

/** List all backup configs for a server. */
export async function listBackupConfigs(serverId) {
  return get(`/api/servers/${serverId}/backup-configs`)
}

/** Create a new backup config. */
export async function createBackupConfig(serverId, data) {
  return post(`/api/servers/${serverId}/backup-configs`, data)
}

/** Update an existing backup config (re-registers any schedule on the backend). */
export async function updateBackupConfig(serverId, configId, data) {
  return put(`/api/servers/${serverId}/backup-configs/${configId}`, data)
}

/**
 * Delete a backup config (and its snapshot records).
 *
 * When `purge` is true, the backend also deletes archive files on disk that
 * are owned by this config's snapshot records. The backend always returns
 * `{ deleted_files, retained_files, retained_paths }` so the UI can surface
 * what actually happened on disk (see plan §6 "Purge UX (no silent orphans)").
 */
export async function deleteBackupConfig(serverId, configId, { purge = false } = {}) {
  const suffix = purge ? '?purge=1' : ''
  return del(`/api/servers/${serverId}/backup-configs/${configId}${suffix}`)
}

/** List all snapshots for a server, newest first (see backend sorting). */
export async function listSnapshots(serverId) {
  return get(`/api/servers/${serverId}/snapshots`)
}

/**
 * Get the stats-strip summary (total count, total bytes, last snapshot,
 * next scheduled fire time).
 */
export async function getBackupSummary(serverId) {
  return get(`/api/servers/${serverId}/backup-summary`)
}

/**
 * Build a download URL for a given snapshot. Returning a URL rather than
 * fetching keeps the browser in charge of the streamed download and gives
 * us `as_attachment=True` semantics for free.
 */
export function snapshotDownloadUrl(serverId, snapshotId, format = 'tar') {
  const base = `/api/servers/${serverId}/snapshots/${snapshotId}/download`
  return format === 'zip' ? `${base}?format=zip` : base
}

/** Delete a snapshot archive (file + record). */
export async function deleteSnapshot(serverId, snapshotId) {
  return del(`/api/servers/${serverId}/snapshots/${snapshotId}`)
}

/**
 * Trigger a manual backup. Returns `{ job_id }` — poll `getBackupJob` until
 * `active: false` to surface completion.
 */
export async function runBackupConfig(serverId, configId) {
  return post(`/api/servers/${serverId}/backup-configs/${configId}/run`)
}

/**
 * Trigger a one-off backup with no pre-existing config.
 * `storagePath` is required; the rest default on the backend.
 * Returns `{ job_id }`.
 */
export async function runQuickBackup(serverId, { storagePath, compress = true, flush = true, shutdown = false }) {
  return post(`/api/servers/${serverId}/backup-quick`, { storagePath, compress, flush, shutdown })
}

/**
 * Trigger a restore from an existing snapshot.
 * `mode` is one of `"in_place"` (overlay copy) or `"reset"` (atomic swap).
 * Returns `{ job_id }`.
 */
export async function restoreSnapshot(serverId, snapshotId, mode) {
  return post(`/api/servers/${serverId}/snapshots/${snapshotId}/restore`, { mode })
}

/**
 * Poll a backup/restore job by id. Backend returns `{ active, phase, ... }`.
 * Globally-unique uuid so no server scoping is needed.
 */
export async function getBackupJob(jobId) {
  return get(`/api/backup-jobs/${jobId}`)
}

/**
 * Upload a world archive (zip / tar / tar.gz) to replace the server's active
 * world. The raw file is the request body; the backend streams it to disk,
 * validates it, then runs the import as a job. Returns `{ job_id }` — poll
 * `getBackupJob` for the server-side extract/convert/swap phases.
 *
 * Uses XMLHttpRequest (not fetch) for the one thing fetch can't give us here:
 * upload progress events. Worlds are large, so `onProgress(pct)` drives a real
 * progress bar during the upload before the job even starts.
 *
 * @param {string} serverId
 * @param {File} file
 * @param {object} [opts]
 * @param {(pct:number)=>void} [opts.onProgress] 0–100, or -1 when indeterminate
 * @param {(abort:()=>void)=>void} [opts.registerAbort] receives a cancel fn
 * @returns {Promise<{job_id:string}>}
 */
export function uploadWorld(serverId, file, { onProgress, registerAbort } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const url = `/api/servers/${serverId}/world-import?filename=${encodeURIComponent(file.name)}`
    xhr.open('POST', url)
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
