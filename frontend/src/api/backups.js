/**
 * Backup Manager API Client
 *
 * Wraps the per-server backup endpoints exposed by backend/backups/routes.py.
 * Job-progress polling (`getBackupJob`) is keyed on a globally-unique job id
 * returned by the `run` and `restore` endpoints — no server scoping needed.
 */

import { get, post, put, del } from './client'

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
export function snapshotDownloadUrl(serverId, snapshotId) {
  return `/api/servers/${serverId}/snapshots/${snapshotId}/download`
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
