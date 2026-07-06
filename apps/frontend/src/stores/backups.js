/**
 * Backup Manager Store (setup syntax, parallels stores/server.js).
 *
 * Owns:
 *   - configs, snapshots, summary
 *   - the Manage Configs slide-in panel state + editor draft
 *   - the Restore Mode + Delete Config modal state
 *   - active backup/restore job polling (1s interval, scoped to a single in-flight job)
 *
 * The store is designed to coexist with the parent server store: it reads
 * the route's :id via the existing server store's `currentServerId` so the
 * page component doesn't have to thread it through props.
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  listBackupConfigs,
  createBackupConfig,
  updateBackupConfig,
  deleteBackupConfig,
  listSnapshots,
  getBackupSummary,
  deleteSnapshot,
  runBackupConfig,
  runQuickBackup as runQuickBackupApi,
  restoreSnapshot,
  getBackupJob,
  uploadWorld
} from '../api/backups'
import { useServerStore } from './server'
import { useToast } from '../composables/useToast'

const JOB_POLL_INTERVAL_MS = 1000

const FREQUENCY_PRESETS = [1, 6, 12, 24, 168]

const DEFAULT_CONFIG_DRAFT = () => ({
  id: null,
  name: '',
  storagePath: '',
  maxSnapshots: 7,
  flush: true,
  shutdown: false,
  compress: true,
  exclusions: '',
  schedule: {
    enabled: true,
    frequencyHours: 24,
    timeOfDay: '03:00'
  }
})

function draftFromConfig(config) {
  if (!config) return DEFAULT_CONFIG_DRAFT()
  const exclusions = Array.isArray(config.exclusions) ? config.exclusions.join('\n') : ''
  return {
    id: config.id,
    name: config.name || '',
    storagePath: config.storagePath || '',
    maxSnapshots: typeof config.maxSnapshots === 'number' ? config.maxSnapshots : 7,
    flush: config.flush !== false,
    shutdown: Boolean(config.shutdown),
    compress: config.compress !== false,
    exclusions,
    schedule: {
      enabled: Boolean(config.schedule?.enabled),
      frequencyHours: typeof config.schedule?.frequencyHours === 'number'
        ? config.schedule.frequencyHours
        : 24,
      timeOfDay: config.schedule?.timeOfDay || '03:00'
    }
  }
}

function draftToPayload(draft) {
  const exclusions = String(draft.exclusions || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  return {
    name: draft.name.trim(),
    storagePath: draft.storagePath.trim(),
    maxSnapshots: Number(draft.maxSnapshots) || 0,
    flush: Boolean(draft.flush),
    shutdown: Boolean(draft.shutdown),
    compress: Boolean(draft.compress),
    exclusions,
    schedule: {
      enabled: Boolean(draft.schedule.enabled),
      frequencyHours: Number(draft.schedule.frequencyHours) || 24,
      timeOfDay: draft.schedule.timeOfDay || '03:00'
    }
  }
}

export const useBackupsStore = defineStore('backups', () => {
  const serverStore = useServerStore()
  const toast = useToast()

  // ---------- State ----------
  const configs = ref([])
  const snapshots = ref([])
  const summary = ref(null)

  const loading = ref(false)
  const configsLoading = ref(false)
  const snapshotsLoading = ref(false)
  const summaryLoading = ref(false)
  const error = ref(null)

  // Manage configs panel
  const showManagePanel = ref(false)
  const editingConfigId = ref(null) // null when creating
  const draft = ref(DEFAULT_CONFIG_DRAFT())
  const savingConfig = ref(false)
  const draftError = ref(null)

  // Delete-config modal
  const showDeleteConfigModal = ref(false)
  const configToDelete = ref(null)
  const deletingConfig = ref(false)
  // Retained-files banner — set after a non-purge delete that left files on
  // disk. The page renders a non-dismissable info panel listing the paths so
  // the user can clean them up later (no silent orphans).
  const retainedFilesBanner = ref(null)

  // Restore-mode modal
  const showRestoreModal = ref(false)
  const snapshotToRestore = ref(null)

  // Snapshot delete confirmation (lightweight — handled inline)
  const snapshotToDelete = ref(null)
  const showDeleteSnapshotModal = ref(false)
  const deletingSnapshot = ref(false)

  // Quick-backup modal (config-free one-off backup)
  const showQuickBackupModal = ref(false)

  // Import-world modal (upload an archive to replace the active world)
  const showImportWorldModal = ref(false)
  const importUploading = ref(false)
  const importUploadPct = ref(0) // 0–100, or -1 when indeterminate
  let importAbort = null

  // Active job tracking (one in-flight backup/restore per view at a time)
  // `targetConfigId` and `targetSnapshotId` are nullable hints used by the
  // page to disable destructive actions on the row(s) currently in flight.
  const activeJob = ref(null)
  let jobPollTimerId = null

  // Per-config "running now" indicator (set when user clicks Back up now)
  const runningConfigId = ref(null)

  // ---------- Helpers ----------

  const serverId = computed(() => serverStore.currentServerId)

  const sortedConfigs = computed(() => {
    return [...configs.value].sort((a, b) => {
      const an = (a?.name || '').toLowerCase()
      const bn = (b?.name || '').toLowerCase()
      if (an < bn) return -1
      if (an > bn) return 1
      return 0
    })
  })

  const snapshotsByConfigId = computed(() => {
    const map = new Map()
    for (const snap of snapshots.value) {
      const arr = map.get(snap.configId) || []
      arr.push(snap)
      map.set(snap.configId, arr)
    }
    return map
  })

  function configById(configId) {
    return configs.value.find((c) => c.id === configId) || null
  }

  function isJobAgainstSnapshot(snapshotId) {
    if (!activeJob.value?.active) return false
    return activeJob.value.snapshotId === snapshotId
  }

  function isJobAgainstConfig(configId) {
    if (!activeJob.value?.active) return false
    return activeJob.value.configId === configId
  }

  // ---------- Loaders ----------

  async function loadConfigs() {
    if (!serverId.value) return
    configsLoading.value = true
    try {
      const list = await listBackupConfigs(serverId.value)
      configs.value = Array.isArray(list) ? list : []
    } catch (err) {
      console.error('Failed to load backup configs:', err)
      error.value = err?.message || 'Failed to load backup configs'
    } finally {
      configsLoading.value = false
    }
  }

  async function loadSnapshots() {
    if (!serverId.value) return
    snapshotsLoading.value = true
    try {
      const list = await listSnapshots(serverId.value)
      snapshots.value = Array.isArray(list) ? list : []
    } catch (err) {
      console.error('Failed to load snapshots:', err)
      error.value = err?.message || 'Failed to load snapshots'
    } finally {
      snapshotsLoading.value = false
    }
  }

  async function loadSummary() {
    if (!serverId.value) return
    summaryLoading.value = true
    try {
      summary.value = await getBackupSummary(serverId.value)
    } catch (err) {
      console.error('Failed to load backup summary:', err)
      // Summary failures are non-critical — keep the page usable.
    } finally {
      summaryLoading.value = false
    }
  }

  async function loadAll() {
    if (!serverId.value) return
    loading.value = true
    error.value = null
    try {
      await Promise.all([loadConfigs(), loadSnapshots(), loadSummary()])
    } finally {
      loading.value = false
    }
  }

  // ---------- Manage Configs panel ----------

  const defaultStoragePath = computed(() => summary.value?.defaultStoragePath || '')

  function openCreateConfig() {
    editingConfigId.value = null
    draft.value = { ...DEFAULT_CONFIG_DRAFT(), storagePath: defaultStoragePath.value }
    draftError.value = null
    showManagePanel.value = true
  }

  function openEditConfig(config) {
    editingConfigId.value = config.id
    draft.value = draftFromConfig(config)
    draftError.value = null
    showManagePanel.value = true
  }

  function closeManagePanel() {
    if (savingConfig.value) return
    showManagePanel.value = false
    editingConfigId.value = null
    draft.value = DEFAULT_CONFIG_DRAFT()
    draftError.value = null
  }

  async function saveConfigDraft() {
    if (!serverId.value || savingConfig.value) return
    const payload = draftToPayload(draft.value)
    if (!payload.name) {
      draftError.value = 'Name is required.'
      return
    }
    savingConfig.value = true
    draftError.value = null
    try {
      if (editingConfigId.value) {
        await updateBackupConfig(serverId.value, editingConfigId.value, payload)
        toast.success('Backup config updated', 'Backups')
      } else {
        await createBackupConfig(serverId.value, payload)
        toast.success('Backup config created', 'Backups')
      }
      showManagePanel.value = false
      editingConfigId.value = null
      draft.value = DEFAULT_CONFIG_DRAFT()
      await Promise.all([loadConfigs(), loadSummary()])
    } catch (err) {
      console.error('Failed to save backup config:', err)
      draftError.value = err?.message || 'Failed to save backup config'
    } finally {
      savingConfig.value = false
    }
  }

  // ---------- Delete config (with explicit purge UX) ----------

  function requestDeleteConfig(config) {
    configToDelete.value = config
    showDeleteConfigModal.value = true
  }

  function cancelDeleteConfig() {
    if (deletingConfig.value) return
    showDeleteConfigModal.value = false
    configToDelete.value = null
  }

  /**
   * Confirm-delete carries the explicit `purge` boolean from the modal
   * (unchecked by default per plan §6 — "Purge UX (no silent orphans)").
   * Without `purge` checked the request omits the query param entirely and
   * any retained-files banner the backend returns is surfaced as an info
   * toast so the user can see what's still on disk.
   */
  async function confirmDeleteConfig({ purge }) {
    if (!serverId.value || !configToDelete.value || deletingConfig.value) return
    const config = configToDelete.value
    deletingConfig.value = true
    try {
      const res = await deleteBackupConfig(serverId.value, config.id, { purge })
      const deletedFiles = res?.deleted_files ?? 0
      const retainedFiles = res?.retained_files ?? 0
      const retainedPaths = Array.isArray(res?.retained_paths) ? res.retained_paths : []
      const banner = retainedFiles > 0 ? { configName: config.name, retainedFiles, retainedPaths } : null
      retainedFilesBanner.value = banner
      if (retainedFiles > 0) {
        toast.info(
          `${retainedFiles} archive file${retainedFiles === 1 ? '' : 's'} kept on disk for "${config.name}".`,
          'Backups'
        )
      } else if (deletedFiles > 0) {
        toast.success(
          `Config deleted. Removed ${deletedFiles} archive file${deletedFiles === 1 ? '' : 's'} on disk.`,
          'Backups'
        )
      } else {
        toast.success('Backup config deleted', 'Backups')
      }
      showDeleteConfigModal.value = false
      configToDelete.value = null
      await Promise.all([loadConfigs(), loadSnapshots(), loadSummary()])
    } catch (err) {
      console.error('Failed to delete backup config:', err)
      toast.error(err?.message || 'Failed to delete backup config', 'Backups')
    } finally {
      deletingConfig.value = false
    }
  }

  function dismissRetainedFilesBanner() {
    retainedFilesBanner.value = null
  }

  // ---------- Run backup (manual) ----------

  async function runBackup(configId) {
    if (!serverId.value || !configId) return
    if (runningConfigId.value) return // one manual run at a time per view
    runningConfigId.value = configId
    try {
      const res = await runBackupConfig(serverId.value, configId)
      const jobId = res?.job_id
      if (!jobId) {
        toast.error('Backup did not return a job id', 'Backups')
        return
      }
      activeJob.value = {
        id: jobId,
        kind: 'backup',
        configId,
        snapshotId: null,
        active: true,
        phase: 'starting'
      }
      startJobPolling()
      toast.info('Backup started', 'Backups')
    } catch (err) {
      console.error('Failed to start backup:', err)
      toast.error(err?.message || 'Failed to start backup', 'Backups')
    } finally {
      // runningConfigId is cleared when polling finalises; the disable
      // happens during the active poll loop, not just the initial POST.
      if (!activeJob.value?.active) runningConfigId.value = null
    }
  }

  // ---------- Quick backup (no config) ----------

  function openQuickBackupModal() {
    showQuickBackupModal.value = true
  }

  function closeQuickBackupModal() {
    if (activeJob.value?.active) return
    showQuickBackupModal.value = false
  }

  async function runQuickBackup({ storagePath, compress, flush, shutdown }) {
    if (!serverId.value) return
    try {
      const res = await runQuickBackupApi(serverId.value, { storagePath, compress, flush, shutdown })
      const jobId = res?.job_id
      if (!jobId) {
        toast.error('Quick backup did not return a job id', 'Backups')
        return
      }
      activeJob.value = {
        id: jobId,
        kind: 'backup',
        configId: null,
        snapshotId: null,
        active: true,
        phase: 'starting'
      }
      showQuickBackupModal.value = false
      startJobPolling()
      toast.info('Quick backup started', 'Backups')
    } catch (err) {
      console.error('Failed to start quick backup:', err)
      toast.error(err?.message || 'Failed to start quick backup', 'Backups')
    }
  }

  // ---------- Import world (upload) ----------

  function openImportWorldModal() {
    showImportWorldModal.value = true
  }

  function closeImportWorldModal() {
    if (importUploading.value || activeJob.value?.active) return
    showImportWorldModal.value = false
  }

  function cancelImportUpload() {
    if (typeof importAbort === 'function') importAbort()
  }

  /**
   * Upload a world archive and start the import job. The upload itself shows a
   * determinate progress bar (importUploadPct); once it lands the job_id takes
   * over via the shared polling loop, which surfaces the server-side
   * extract/convert/swap phases. The server is stopped and the active world
   * replaced — the modal warns about both before the user gets here.
   */
  async function importWorld(file) {
    if (!serverId.value || !file) return
    if (importUploading.value || activeJob.value?.active) return
    importUploading.value = true
    importUploadPct.value = 0
    try {
      const res = await uploadWorld(serverId.value, file, {
        onProgress: (pct) => { importUploadPct.value = pct },
        registerAbort: (abort) => { importAbort = abort }
      })
      const jobId = res?.job_id
      if (!jobId) {
        toast.error('World import did not return a job id', 'Backups')
        return
      }
      activeJob.value = {
        id: jobId,
        kind: 'world_import',
        configId: null,
        snapshotId: null,
        active: true,
        phase: 'starting'
      }
      showImportWorldModal.value = false
      startJobPolling()
      toast.info('World import started', 'Backups')
    } catch (err) {
      // A user-initiated cancel surfaces as status 0 / "Upload cancelled".
      if (err?.message === 'Upload cancelled') {
        toast.info('Upload cancelled', 'Backups')
      } else {
        console.error('Failed to import world:', err)
        toast.error(err?.message || 'Failed to import world', 'Backups')
      }
    } finally {
      importUploading.value = false
      importUploadPct.value = 0
      importAbort = null
    }
  }

  // ---------- Restore ----------

  function requestRestoreSnapshot(snapshot) {
    snapshotToRestore.value = snapshot
    showRestoreModal.value = true
  }

  function cancelRestore() {
    if (activeJob.value?.kind === 'restore' && activeJob.value.active) return
    showRestoreModal.value = false
    snapshotToRestore.value = null
  }

  async function confirmRestore(mode) {
    if (!serverId.value || !snapshotToRestore.value) return
    const snap = snapshotToRestore.value
    try {
      const res = await restoreSnapshot(serverId.value, snap.id, mode)
      const jobId = res?.job_id
      if (!jobId) {
        toast.error('Restore did not return a job id', 'Backups')
        return
      }
      activeJob.value = {
        id: jobId,
        kind: 'restore',
        configId: snap.configId,
        snapshotId: snap.id,
        active: true,
        phase: 'starting',
        mode
      }
      startJobPolling()
      showRestoreModal.value = false
      snapshotToRestore.value = null
      toast.info(mode === 'reset' ? 'Restore (reset) started' : 'Restore started', 'Backups')
    } catch (err) {
      console.error('Failed to start restore:', err)
      toast.error(err?.message || 'Failed to start restore', 'Backups')
    }
  }

  // ---------- Snapshot delete (inline confirm) ----------

  function requestDeleteSnapshot(snapshot) {
    snapshotToDelete.value = snapshot
    showDeleteSnapshotModal.value = true
  }

  function cancelDeleteSnapshot() {
    if (deletingSnapshot.value) return
    showDeleteSnapshotModal.value = false
    snapshotToDelete.value = null
  }

  async function confirmDeleteSnapshot() {
    if (!serverId.value || !snapshotToDelete.value || deletingSnapshot.value) return
    const snap = snapshotToDelete.value
    deletingSnapshot.value = true
    try {
      await deleteSnapshot(serverId.value, snap.id)
      toast.success('Snapshot deleted', 'Backups')
      showDeleteSnapshotModal.value = false
      snapshotToDelete.value = null
      await Promise.all([loadSnapshots(), loadSummary()])
    } catch (err) {
      console.error('Failed to delete snapshot:', err)
      toast.error(err?.message || 'Failed to delete snapshot', 'Backups')
    } finally {
      deletingSnapshot.value = false
    }
  }

  // ---------- Job polling ----------

  function startJobPolling() {
    stopJobPolling()
    if (!activeJob.value?.id) return
    pollJob()
    jobPollTimerId = setInterval(pollJob, JOB_POLL_INTERVAL_MS)
  }

  function stopJobPolling() {
    if (jobPollTimerId) {
      clearInterval(jobPollTimerId)
      jobPollTimerId = null
    }
  }

  async function pollJob() {
    const job = activeJob.value
    if (!job?.id) {
      stopJobPolling()
      return
    }
    try {
      const status = await getBackupJob(job.id)
      // Merge so we don't lose the locally-tracked kind/configId/snapshotId.
      activeJob.value = {
        ...job,
        ...status
      }
      if (!status?.active) {
        stopJobPolling()
        runningConfigId.value = null
        const kind = job.kind === 'restore'
          ? 'Restore'
          : job.kind === 'world_import'
            ? 'World import'
            : 'Backup'
        const phase = status?.phase || 'done'
        if (phase === 'failed' || status?.error) {
          toast.error(status?.error || `${kind} failed`, 'Backups')
        } else {
          toast.success(`${kind} completed`, 'Backups')
        }
        // Refresh data once the job lands.
        await Promise.all([loadSnapshots(), loadSummary(), loadConfigs()])
        // Keep activeJob around briefly so the UI can render the final
        // phase ("done"/"failed"), then drop it on the next tick.
        setTimeout(() => {
          if (activeJob.value && !activeJob.value.active) {
            activeJob.value = null
          }
        }, 1500)
      }
    } catch (err) {
      console.error('Failed to poll backup job:', err)
      // Soft-fail: stop polling rather than spam errors.
      stopJobPolling()
      activeJob.value = null
      runningConfigId.value = null
    }
  }

  // ---------- Filter / search state for the page ----------

  const search = ref('')
  const configFilter = ref('all') // 'all' or a config id
  const typeFilter = ref('all') // 'all' | 'backup' | 'safety' | 'restore'

  const filteredSnapshots = computed(() => {
    const q = search.value.trim().toLowerCase()
    return snapshots.value.filter((snap) => {
      if (configFilter.value === '__manual__' && snap.configId !== null) return false
      if (configFilter.value !== 'all' && configFilter.value !== '__manual__' && snap.configId !== configFilter.value) return false
      if (typeFilter.value !== 'all' && snap.type !== typeFilter.value) return false
      if (!q) return true
      const fields = [snap.fileName, snap.message, configById(snap.configId)?.name].filter(Boolean)
      return fields.some((f) => String(f).toLowerCase().includes(q))
    })
  })

  // ---------- Lifecycle hooks for the page ----------

  function resetState() {
    stopJobPolling()
    configs.value = []
    snapshots.value = []
    summary.value = null
    error.value = null
    showManagePanel.value = false
    editingConfigId.value = null
    draft.value = DEFAULT_CONFIG_DRAFT()
    savingConfig.value = false
    draftError.value = null
    showDeleteConfigModal.value = false
    configToDelete.value = null
    deletingConfig.value = false
    showRestoreModal.value = false
    snapshotToRestore.value = null
    snapshotToDelete.value = null
    showDeleteSnapshotModal.value = false
    deletingSnapshot.value = false
    showQuickBackupModal.value = false
    showImportWorldModal.value = false
    importUploading.value = false
    importUploadPct.value = 0
    importAbort = null
    activeJob.value = null
    runningConfigId.value = null
    search.value = ''
    configFilter.value = 'all'
    typeFilter.value = 'all'
    retainedFilesBanner.value = null
  }

  return {
    // state
    configs,
    snapshots,
    summary,
    loading,
    configsLoading,
    snapshotsLoading,
    summaryLoading,
    error,
    showManagePanel,
    editingConfigId,
    draft,
    savingConfig,
    draftError,
    showDeleteConfigModal,
    configToDelete,
    deletingConfig,
    showQuickBackupModal,
    showImportWorldModal,
    importUploading,
    importUploadPct,
    showRestoreModal,
    snapshotToRestore,
    snapshotToDelete,
    showDeleteSnapshotModal,
    deletingSnapshot,
    activeJob,
    runningConfigId,
    retainedFilesBanner,
    search,
    configFilter,
    typeFilter,
    // getters
    sortedConfigs,
    snapshotsByConfigId,
    filteredSnapshots,
    defaultStoragePath,
    // constants
    frequencyPresets: FREQUENCY_PRESETS,
    // actions
    loadConfigs,
    loadSnapshots,
    loadSummary,
    loadAll,
    openCreateConfig,
    openEditConfig,
    closeManagePanel,
    saveConfigDraft,
    requestDeleteConfig,
    cancelDeleteConfig,
    confirmDeleteConfig,
    dismissRetainedFilesBanner,
    runBackup,
    openQuickBackupModal,
    closeQuickBackupModal,
    runQuickBackup,
    openImportWorldModal,
    closeImportWorldModal,
    cancelImportUpload,
    importWorld,
    requestRestoreSnapshot,
    cancelRestore,
    confirmRestore,
    requestDeleteSnapshot,
    cancelDeleteSnapshot,
    confirmDeleteSnapshot,
    isJobAgainstSnapshot,
    isJobAgainstConfig,
    configById,
    stopJobPolling,
    resetState
  }
})
