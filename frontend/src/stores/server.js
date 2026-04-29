import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import { installMod, installModpack, getModpackInstallProgress } from '../api/modrinth'
import {
  getServer,
  getServers,
  getInstalledMods,
  removeMod,
  getServerLogs,
  startServer,
  stopServer,
  restartServer,
  updateServerSettings,
  sendServerCommand,
  browseServerFiles,
  createBackup,
  getBackups,
  restoreBackup,
  deleteBackup,
  deleteServer,
  getServerFile,
  saveServerFile
} from '../api/servers'
import { useToast } from '../composables/useToast'

const MODPACK_STAGE_LABELS = {
  starting: 'Starting install...',
  resolving: 'Resolving modpack version...',
  cleaning: 'Cleaning old modpack files...',
  downloading_pack: 'Downloading modpack archive...',
  checking_availability: 'Checking file availability...',
  installing_files: 'Downloading mods...',
  extracting_overrides: 'Extracting override files...',
  done: 'Finishing up...'
}

const TEXT_FILE_EXTENSIONS = new Set([
  'txt', 'json', 'properties', 'yml', 'yaml', 'toml', 'cfg', 'conf', 'log', 'md'
])

function isTextFile(path) {
  if (!path || typeof path !== 'string') return false
  const segments = path.toLowerCase().split('.')
  const extension = segments.pop() || ''
  return TEXT_FILE_EXTENSIONS.has(extension)
}

export const useServerStore = defineStore('server', () => {
  const router = useRouter()
  const toast = useToast()

  // ---------- State ----------
  // Pushed by ServerLayout via watchers with immediate: true. We do NOT call
  // useRoute() here — setup-store route context is fragile under HMR and
  // call-ordering changes. Layout owns route → store synchronization.
  const currentServerId = ref(null)
  const currentRouteName = ref(null)
  const serversList = ref([])

  const server = ref(null)
  const serverLoading = ref(true)
  const modsLoading = ref(false)
  const logsLoading = ref(false)
  const installedMods = ref([])
  const modSearch = ref('')
  const logs = ref({ stdout: [], stderr: [], running: false })
  const serverSettings = ref(null)
  const showModBrowser = ref(false)
  const showJavaModal = ref(false)
  const pendingJavaAction = ref(null)
  const showModpackBrowser = ref(false)
  const showConfirmModal = ref(false)
  const confirmModalData = ref({})
  const modToRemove = ref(null)
  const installLoading = ref(false)
  const modpackInstalling = ref(false)
  const actionState = ref({ start: false, stop: false, restart: false })
  const consoleCommand = ref('')
  const commandSending = ref(false)
  const backups = ref([])
  const backupLoading = ref(false)
  const fileBrowser = ref({ currentPath: '', entries: [], loading: false, error: null })
  const fileEditor = ref({ path: null, content: '', originalContent: '', loading: false, saving: false, error: null })
  const backupToRestore = ref(null)
  const showBackupRestoreModal = ref(false)
  const restoringBackup = ref(false)
  const backupToDelete = ref(null)
  const showBackupDeleteModal = ref(false)
  const deletingBackup = ref(false)
  const showDeleteServerModal = ref(false)
  const deletingServer = ref(false)
  const modpackProgress = ref(null)
  const showModpackInstallConfirmModal = ref(false)
  const pendingModpackInstall = ref(null)
  const modpackCreateBackup = ref(true)
  const showMissingModsConfirmModal = ref(false)
  const pendingMissingModsInstall = ref(null)
  const missingModsReport = ref([])
  const showUncertainModsModal = ref(false)
  const uncertainModsReport = ref([])
  const pendingUncertainModpackData = ref(null)

  // ---------- Private helpers (not returned) ----------
  const defaultSettings = (data = {}) => ({
    name: data.name || 'Minecraft Server',
    port: data.port ?? 25565,
    serverIp: data.serverIp || '',
    motd: data.motd || 'A Minecraft Server',
    bugReportLink: data.bugReportLink || '',
    maxPlayers: data.maxPlayers ?? 20,
    difficulty: data.difficulty || 'normal',
    gamemode: data.gamemode || 'survival',
    forceGamemode: data.forceGamemode ?? false,
    hardcore: data.hardcore ?? false,
    allowFlight: data.allowFlight ?? false,
    pvp: data.pvp ?? true,
    spawnProtection: data.spawnProtection ?? 16,
    commandBlocks: data.commandBlocks ?? true,
    whitelist: data.whitelist ?? false,
    enforceWhitelist: data.enforceWhitelist ?? false,
    functionPermissionLevel: data.functionPermissionLevel ?? 2,
    opPermissionLevel: data.opPermissionLevel ?? 4,
    playerIdleTimeout: data.playerIdleTimeout ?? 0,
    pauseWhenEmptySeconds: data.pauseWhenEmptySeconds ?? 60,
    onlineMode: data.onlineMode ?? true,
    enforceSecureProfile: data.enforceSecureProfile ?? true,
    hideOnlinePlayers: data.hideOnlinePlayers ?? false,
    preventProxyConnections: data.preventProxyConnections ?? false,
    logIps: data.logIps ?? true,
    acceptsTransfers: data.acceptsTransfers ?? false,
    enableStatus: data.enableStatus ?? true,
    statusHeartbeatInterval: data.statusHeartbeatInterval ?? 0,
    broadcastConsoleToOps: data.broadcastConsoleToOps ?? true,
    broadcastRconToOps: data.broadcastRconToOps ?? true,
    enableCodeOfConduct: data.enableCodeOfConduct ?? false,
    enableJmxMonitoring: data.enableJmxMonitoring ?? false,
    enableQuery: data.enableQuery ?? false,
    queryPort: data.queryPort ?? data.port ?? 25565,
    enableRcon: data.enableRcon ?? false,
    rconPort: data.rconPort ?? 25575,
    rconPassword: data.rconPassword || '',
    rateLimit: data.rateLimit ?? 0,
    networkCompressionThreshold: data.networkCompressionThreshold ?? 256,
    resourcePack: data.resourcePack || '',
    resourcePackPrompt: data.resourcePackPrompt || '',
    resourcePackSha1: data.resourcePackSha1 || '',
    resourcePackId: data.resourcePackId || '',
    requireResourcePack: data.requireResourcePack ?? false,
    initialEnabledPacks: data.initialEnabledPacks || 'vanilla',
    initialDisabledPacks: data.initialDisabledPacks || '',
    textFilteringConfig: data.textFilteringConfig || '',
    textFilteringVersion: data.textFilteringVersion ?? 0,
    viewDistance: data.viewDistance ?? 10,
    simulationDistance: data.simulationDistance ?? 10,
    memory: data.memory ?? 4,
    levelName: data.levelName || 'world',
    levelType: data.levelType || 'default',
    seed: data.seed || '',
    generatorSettings: data.generatorSettings ?? '',
    maxWorldSize: data.maxWorldSize ?? 29999984,
    generateStructures: data.generateStructures ?? true,
    spawnAnimals: data.spawnAnimals ?? true,
    spawnMonsters: data.spawnMonsters ?? true,
    spawnNpcs: data.spawnNpcs ?? true,
    entityBroadcastRangePercentage: data.entityBroadcastRangePercentage ?? 100,
    maxChainedNeighborUpdates: data.maxChainedNeighborUpdates ?? 1000000,
    maxTickTime: data.maxTickTime ?? 60000,
    syncChunkWrites: data.syncChunkWrites ?? true,
    useNativeTransport: data.useNativeTransport ?? true,
    regionFileCompression: data.regionFileCompression || 'deflate'
  })

  const formatMissingModsDescription = (missingFiles = []) => {
    if (!Array.isArray(missingFiles) || !missingFiles.length) return ''
    const preview = missingFiles.slice(0, 8).map((i) => `- ${i.path}: ${i.reason}`).join('\n')
    const remaining = missingFiles.length - preview.split('\n').length
    const suffix = remaining > 0 ? `\n...and ${remaining} more.` : ''
    return `The following files could not be downloaded:\n${preview}${suffix}\n\nInstall anyway without these files?`
  }

  // ---------- Computeds (getters) ----------
  const modpackProgressLabel = computed(() => {
    const p = modpackProgress.value
    if (!p?.active) return ''
    const stage = MODPACK_STAGE_LABELS[p.stage] || p.stage || 'Working...'
    if (p.stage === 'installing_files' && p.total > 0) {
      return `${stage} (${p.current}/${p.total})`
    }
    return stage
  })

  const modpackProgressPercent = computed(() => {
    const p = modpackProgress.value
    if (!p?.active || !p.total) return 0
    return Math.round((p.current / p.total) * 100)
  })

  const serverStatus = computed(() => {
    const loaderName = server.value?.loader
      ? server.value.loader.charAt(0).toUpperCase() + server.value.loader.slice(1)
      : 'Unknown'

    return {
      name: server.value?.name || 'Minecraft Server',
      status: server.value?.runtime?.status || server.value?.status || 'pending',
      uptime: server.value?.runtime?.uptime || '—',
      version: server.value?.version || '—',
      loader: loaderName,
      players: {
        online: server.value?.runtime?.players?.online ?? 0,
        max: server.value?.maxPlayers ?? server.value?.runtime?.players?.max ?? 0
      },
      tps: server.value?.runtime?.tps ?? 20
    }
  })

  const canEditSettings = computed(() => serverStatus.value.status !== 'running')

  const ramMetrics = computed(() => {
    const runtimeRam = server.value?.runtime?.ram
    const runtimeLimit = typeof runtimeRam?.limitGB === 'number' ? runtimeRam.limitGB : null
    const configuredTotal = Number(server.value?.memory ?? serverSettings.value?.memory ?? 0)
    let total = runtimeLimit ?? configuredTotal
    if (!Number.isFinite(total) || total <= 0) total = 1
    let used = 0
    if (runtimeRam) {
      if (typeof runtimeRam.usedGB === 'number') used = runtimeRam.usedGB
      else if (typeof runtimeRam.usedBytes === 'number') used = runtimeRam.usedBytes / (1024 ** 3)
      else if (typeof runtimeRam.used === 'number') used = runtimeRam.used
    }
    used = Math.max(0, Math.min(used, total))
    return { used, total, running: serverStatus.value.status === 'running' }
  })

  const filteredMods = computed(() => {
    if (!modSearch.value) return installedMods.value
    return installedMods.value.filter((m) => m.name.toLowerCase().includes(modSearch.value.toLowerCase()))
  })

  const playersDisplay = computed(() => {
    const o = serverStatus.value.players.online
    const m = serverStatus.value.players.max
    return m ? `${o}/${m}` : `${o}`
  })

  const statusLabel = computed(() => {
    const s = serverStatus.value.status
    if (s === 'running') return 'Running'
    if (s === 'stopped') return 'Stopped'
    if (s === 'pending') return 'Install Required'
    if (s === 'installing') return 'Installing'
    if (s === 'failed') return 'Failed'
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Unknown'
  })

  const startLocked = computed(() => ['installing', 'pending'].includes(serverStatus.value.status))

  const startButtonLabel = computed(() => {
    if (serverStatus.value.status === 'installing') return 'Installing…'
    if (serverStatus.value.status === 'pending') return 'Install Required'
    return actionState.value.start ? 'Starting…' : 'Start'
  })

  const activeModpack = computed(() => server.value?.modpack || null)

  const isInstalling = computed(() => installLoading.value || modpackInstalling.value)

  const canSendCommand = computed(() => serverStatus.value.status === 'running' && !!server.value)

  // Description for the missing-mods confirm modal. Computed (not a function)
  // so the template binding stays reactive when missingModsReport changes.
  const missingModsDescriptionText = computed(() => formatMissingModsDescription(missingModsReport.value))

  const hasFileChanges = computed(() => {
    if (!fileEditor.value.path) return false
    return fileEditor.value.content !== fileEditor.value.originalContent
  })

  // ---------- Actions ----------

  async function loadServers() {
    try {
      const list = await getServers()
      if (Array.isArray(list)) {
        serversList.value = list
      }
    } catch {
      // Failure-safe: keep last-known-good state. Switcher pseudo-entry handles empty list.
    }
  }

  async function loadServer(options = {}) {
    const { silent = false } = options
    if (!silent) serverLoading.value = true
    try {
      const data = await getServer(currentServerId.value)
      server.value = data
      const mappedSettings = defaultSettings(data)
      if (!serverSettings.value || currentRouteName.value !== 'ServerSettings') {
        serverSettings.value = mappedSettings
      }
    } catch (error) {
      console.error('Failed to load server:', error)
      toast.error('Could not load server details', 'Error')
    } finally {
      if (!silent) serverLoading.value = false
    }
  }

  async function loadMods() {
    modsLoading.value = true
    try {
      const files = await getInstalledMods(currentServerId.value)
      installedMods.value = files.map((file) => ({
        name: file.name,
        filename: file.name,
        version: file.version || 'local',
        downloads: file.downloads || 'N/A',
        size: file.size,
        updatedAt: file.updatedAt,
        path: file.path,
        source: 'Local',
        category: 'Mods Folder'
      }))
    } catch (error) {
      console.error('Failed to load mods:', error)
      toast.error('Failed to load installed mods', 'Error')
    } finally {
      modsLoading.value = false
    }
  }

  async function loadLogs(limit = 200) {
    if (!server.value || logsLoading.value) return
    logsLoading.value = true
    try {
      logs.value = await getServerLogs(currentServerId.value, { limit })
    } catch (error) {
      console.error('Failed to load logs:', error)
      toast.error('Failed to load console logs', 'Error')
    } finally {
      logsLoading.value = false
    }
  }

  async function loadBackups() {
    backupLoading.value = true
    try {
      backups.value = await getBackups(currentServerId.value)
    } catch (error) {
      console.error('Failed to load backups:', error)
      toast.error('Failed to load backups', 'Backups')
    } finally {
      backupLoading.value = false
    }
  }

  async function refreshAll() {
    await Promise.all([loadServer(), loadMods(), loadBackups()])
  }

  async function createBackupAction() {
    if (backupLoading.value) return
    backupLoading.value = true
    try {
      await createBackup(currentServerId.value)
      toast.success('Backup created successfully', 'Backups')
      await loadBackups()
      // On success, navigate to wherever the backups list lives. Currently
      // the Files page; revisit if backups get their own route.
      router.push({ name: 'ServerFiles', params: { id: currentServerId.value } })
    } catch (error) {
      console.error('Failed to create backup:', error)
      toast.error(error.message || 'Failed to create backup', 'Backups')
    } finally {
      backupLoading.value = false
    }
  }

  function requestRestoreBackup(backup) {
    backupToRestore.value = backup
    showBackupRestoreModal.value = true
  }

  async function confirmRestoreBackup() {
    if (!backupToRestore.value) return
    restoringBackup.value = true
    try {
      const backupId = backupToRestore.value.relativePath.replace(/\.zip$/i, '')
      await restoreBackup(currentServerId.value, backupId)
      toast.success('Backup restored successfully', 'Backups')
      await Promise.all([openFileBrowser(), loadMods()])
    } catch (error) {
      console.error('Failed to restore backup:', error)
      toast.error(error.message || 'Failed to restore backup', 'Backups')
    } finally {
      restoringBackup.value = false
      showBackupRestoreModal.value = false
      backupToRestore.value = null
    }
  }

  function cancelRestoreBackup() {
    showBackupRestoreModal.value = false
    backupToRestore.value = null
  }

  function requestDeleteBackup(backup) {
    backupToDelete.value = backup
    showBackupDeleteModal.value = true
  }

  async function confirmDeleteBackup() {
    if (!backupToDelete.value) return
    deletingBackup.value = true
    try {
      const backupId = backupToDelete.value.relativePath.replace(/\.zip$/i, '')
      await deleteBackup(currentServerId.value, backupId)
      toast.success('Backup deleted', 'Backups')
      await loadBackups()
    } catch (error) {
      console.error('Failed to delete backup:', error)
      toast.error(error.message || 'Failed to delete backup', 'Backups')
    } finally {
      deletingBackup.value = false
      showBackupDeleteModal.value = false
      backupToDelete.value = null
    }
  }

  function cancelDeleteBackup() {
    showBackupDeleteModal.value = false
    backupToDelete.value = null
  }

  async function openFileBrowser(path = '') {
    fileBrowser.value.loading = true
    fileBrowser.value.error = null
    try {
      const data = await browseServerFiles(currentServerId.value, path ? { path } : {})
      fileBrowser.value = { ...data, entries: data.entries, loading: false, error: null }
    } catch (error) {
      console.error('Failed to browse files:', error)
      fileBrowser.value = { currentPath: path, entries: [], loading: false, error: error.message || 'Unable to load files' }
    }
  }

  function enterFileEntry(entry) {
    if (entry.isDir) openFileBrowser(entry.relativePath)
  }

  function goUpDirectory() {
    if (!fileBrowser.value.currentPath) return
    const parts = fileBrowser.value.currentPath.split('/').filter(Boolean)
    parts.pop()
    openFileBrowser(parts.join('/'))
  }

  async function openFile(path) {
    if (!isTextFile(path)) {
      toast.error('Only supported text files can be edited', 'Files')
      return
    }
    fileEditor.value = { path, content: '', originalContent: '', loading: true, saving: false, error: null }
    try {
      const file = await getServerFile(currentServerId.value, path)
      fileEditor.value = { path: file.path, content: file.content, originalContent: file.content, loading: false, saving: false, error: null }
    } catch (error) {
      const message = error?.message || 'Unable to open file'
      fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: message }
      toast.error(message, 'Files')
    }
  }

  async function saveFile() {
    if (!fileEditor.value.path || fileEditor.value.saving) return
    fileEditor.value.saving = true
    fileEditor.value.error = null
    try {
      await saveServerFile(currentServerId.value, fileEditor.value.path, fileEditor.value.content)
      fileEditor.value.originalContent = fileEditor.value.content
      toast.success('File saved', 'Files')
    } catch (error) {
      const message = error?.message || 'Failed to save file'
      fileEditor.value.error = message
      toast.error(message, 'Files')
    } finally {
      fileEditor.value.saving = false
    }
  }

  function closeFile() {
    fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: null }
  }

  function openModBrowser() { showModBrowser.value = true }
  function openModpackBrowser() { showModpackBrowser.value = true }
  function openDeleteServerModal() { showDeleteServerModal.value = true }
  function cancelDeleteServer() { showDeleteServerModal.value = false }

  function goToConsole()  { router.push({ name: 'ServerConsole',  params: { id: currentServerId.value } }) }
  function goToFiles()    { router.push({ name: 'ServerFiles',    params: { id: currentServerId.value } }) }
  function goToSettings() { router.push({ name: 'ServerSettings', params: { id: currentServerId.value } }) }
  function goToMods()     { router.push({ name: 'ServerMods',     params: { id: currentServerId.value } }) }

  async function confirmDeleteServer() {
    deletingServer.value = true
    try {
      await deleteServer(currentServerId.value)
      toast.success('Server deleted', 'Servers')
      await loadServers()
      router.push({ name: 'Servers' })
    } catch (error) {
      console.error('Failed to delete server:', error)
      toast.error(error.message || 'Failed to delete server', 'Server Error')
    } finally {
      deletingServer.value = false
      showDeleteServerModal.value = false
    }
  }

  async function handleInstallMod(modData) {
    if (!server.value) return
    installLoading.value = true
    try {
      await installMod(modData.modId, {
        mc_version: modData.mcVersion,
        loader: modData.loader,
        server_id: currentServerId.value
      })
      showModBrowser.value = false
      toast.success(`${modData.modTitle} installed successfully!`, 'Mod Installed')
      await loadMods()
    } catch (error) {
      console.error('Install failed:', error)
      toast.error(error.message || 'Mod installation failed', 'Installation Failed')
    } finally {
      installLoading.value = false
    }
  }

  function handleUpdateMod(mod) {
    console.log('Update mod placeholder:', mod)
    toast.info('Mod updates coming soon', 'Not Implemented')
  }

  async function handleInstallModpack(modpackData) {
    if (!modpackData) return
    showModpackBrowser.value = false
    pendingModpackInstall.value = modpackData
    showModpackInstallConfirmModal.value = true
  }

  function cancelModpackInstallConfirmation() {
    showModpackInstallConfirmModal.value = false
    pendingModpackInstall.value = null
    modpackCreateBackup.value = true
  }

  async function fetchModpackProgress() {
    try {
      const progress = await getModpackInstallProgress(currentServerId.value)
      modpackProgress.value = progress?.active ? progress : null
    } catch {
      // polling failure is non-critical — silently swallow
    }
  }

  function clearModpackProgress() {
    modpackProgress.value = null
  }

  async function runModpackInstall(modpackData) {
    if (!modpackData) return
    const isRetry = Boolean(modpackData.allowMissing || modpackData.modSideOverrides)
    modpackInstalling.value = true
    if (isRetry) {
      pendingModpackInstall.value = modpackData
      showModpackInstallConfirmModal.value = true
    }
    try {
      const result = await installModpack(modpackData.projectId, {
        mc_version: modpackData.mcVersion,
        loader: modpackData.loader,
        server_id: currentServerId.value,
        clean_install: !isRetry,
        create_backup: isRetry ? false : modpackData.createBackup,
        allow_missing: Boolean(modpackData.allowMissing),
        mod_side_overrides: modpackData.modSideOverrides || null
      })
      showModpackBrowser.value = false
      showModpackInstallConfirmModal.value = false
      pendingModpackInstall.value = null
      modpackCreateBackup.value = true
      const cleanedCount = Array.isArray(result?.cleaned_paths) ? result.cleaned_paths.length : 0
      const missingCount = Array.isArray(result?.missing_files) ? result.missing_files.length : 0
      const cleanedNote = ` Replaced folders: ${cleanedCount}.`
      const missingNote = missingCount ? ` Missing files skipped: ${missingCount}.` : ''
      const backupNote = result?.backup_file ? ` Backup: ${result.backup_file}.` : ''
      toast.success(`${modpackData.title} installed successfully.${cleanedNote}${missingNote}${backupNote}`, 'Modpack Installed')
      if (result?.java_warning) toast.warning(result.java_warning.message, 'Java Version Mismatch')
      await Promise.all([loadServer({ silent: true }), loadMods()])
    } catch (error) {
      const uncertainMods = error?.data?.uncertain_mod_files
      const canContinueWithUncertain = Boolean(error?.data?.can_continue_with_uncertain)
      if (error?.status === 409 && canContinueWithUncertain && Array.isArray(uncertainMods) && uncertainMods.length) {
        showModpackInstallConfirmModal.value = false
        pendingUncertainModpackData.value = modpackData
        uncertainModsReport.value = uncertainMods
        showUncertainModsModal.value = true
        toast.warning('Some mods need a server/client decision before install can continue.', 'Uncertain Mod Side')
        return
      }
      const missingFiles = error?.data?.missing_files
      const canContinue = Boolean(error?.data?.can_continue_with_missing)
      if (!modpackData.allowMissing && error?.status === 409 && canContinue && Array.isArray(missingFiles) && missingFiles.length) {
        showModpackInstallConfirmModal.value = false
        pendingMissingModsInstall.value = { ...modpackData, allowMissing: true }
        missingModsReport.value = missingFiles
        showMissingModsConfirmModal.value = true
        toast.warning(`${missingFiles.length} files could not be downloaded. Choose if you want to continue without them.`, 'Missing Modpack Files')
        return
      }
      showModpackInstallConfirmModal.value = false
      console.error('Modpack install failed:', error)
      toast.error(error.message || 'Modpack installation failed', 'Installation Failed')
    } finally {
      modpackInstalling.value = false
    }
  }

  async function confirmModpackInstall() {
    const data = pendingModpackInstall.value
    if (!data) return
    await runModpackInstall({ ...data, createBackup: modpackCreateBackup.value, allowMissing: false })
  }

  function cancelMissingModsConfirmation() {
    showMissingModsConfirmModal.value = false
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
  }

  async function confirmInstallWithMissingMods() {
    const data = pendingMissingModsInstall.value
    if (!data) return
    showMissingModsConfirmModal.value = false
    await runModpackInstall(data)
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
  }

  function cancelUncertainModsDecision() {
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    toast.info('Modpack install canceled. Unknown mod sides were not confirmed.', 'Install Canceled')
  }

  async function confirmUncertainModsDecision(overrides) {
    const data = pendingUncertainModpackData.value
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    if (!data) return
    await runModpackInstall({ ...data, modSideOverrides: overrides || {} })
  }

  function handleRemoveMod(mod) {
    modToRemove.value = mod
    confirmModalData.value = {
      title: 'Remove Mod',
      message: `Remove ${mod.name}?`,
      description: 'This will delete the mod file from the server. This action cannot be undone.',
      type: 'danger',
      confirmText: 'Remove',
      cancelText: 'Cancel'
    }
    showConfirmModal.value = true
  }

  async function confirmRemoveMod() {
    if (!modToRemove.value) return
    try {
      await removeMod(currentServerId.value, modToRemove.value.filename || modToRemove.value.name)
      toast.success(`${modToRemove.value.name} removed`, 'Mod Removed')
      await loadMods()
    } catch (error) {
      console.error('Failed to remove mod:', error)
      toast.error('Failed to remove mod', 'Error')
    } finally {
      showConfirmModal.value = false
      modToRemove.value = null
    }
  }

  function cancelRemoveMod() {
    showConfirmModal.value = false
    modToRemove.value = null
  }

  async function performServerAction(action, fn, successMessage) {
    if (actionState.value[action]) return
    actionState.value = { ...actionState.value, [action]: true }
    try {
      const result = await fn(currentServerId.value)
      if (result.success) {
        toast.success(successMessage, 'Server Updated')
      } else {
        toast.error(result.message || 'Operation failed', 'Server Error')
      }
    } catch (error) {
      console.error(`Failed to ${action} server:`, error)
      if ((action === 'start' || action === 'restart') && (error.data?.java_missing || error.data?.java_too_old)) {
        pendingJavaAction.value = action
        showJavaModal.value = true
      } else {
        toast.error(error.message || `Failed to ${action} server`, 'Server Error')
      }
    } finally {
      actionState.value = { ...actionState.value, [action]: false }
      await loadServer()
      if (action === 'stop') {
        logs.value = { stdout: [], stderr: [], running: false }
      }
      if (action === 'start' || action === 'restart') {
        await loadLogs()
      }
    }
  }

  function handleStart() { return performServerAction('start', startServer, 'Server start requested') }
  function handleStop()  { return performServerAction('stop',  stopServer,  'Server stop requested') }
  function handleRestart() { return performServerAction('restart', restartServer, 'Server restart requested') }

  function handleJavaInstalled() {
    const action = pendingJavaAction.value
    showJavaModal.value = false
    pendingJavaAction.value = null
    if (action === 'restart') handleRestart()
    else handleStart()
  }

  async function sendConsoleCommand() {
    if (!canSendCommand.value || !consoleCommand.value.trim()) return
    commandSending.value = true
    try {
      await sendServerCommand(currentServerId.value, consoleCommand.value.trim())
      toast.success('Command sent to server', 'Console')
      consoleCommand.value = ''
      await loadLogs()
    } catch (error) {
      console.error('Failed to send command:', error)
      toast.error('Failed to send console command', 'Console Error')
    } finally {
      commandSending.value = false
    }
  }

  async function handleSaveSettings(settings) {
    if (!server.value) return
    try {
      const updated = await updateServerSettings(currentServerId.value, settings)
      server.value = updated
      serverSettings.value = defaultSettings(updated)
      await loadServers()
      toast.success('Settings saved successfully', 'Settings Updated')
    } catch (error) {
      console.error('Failed to save settings:', error)
      toast.error(error.message || 'Failed to save settings', 'Error')
    }
  }

  function resetSettings() {
    if (!server.value) return
    serverSettings.value = defaultSettings(server.value)
  }

  // Performs the same job as the layout's previous resetDashboardState().
  // setup-syntax Pinia stores have no automatic $reset, so we write it explicitly.
  function resetState() {
    server.value = null
    serverSettings.value = null
    installedMods.value = []
    logs.value = { stdout: [], stderr: [], running: false }
    backups.value = []
    fileBrowser.value = { currentPath: '', entries: [], loading: false, error: null }
    fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: null }
    modSearch.value = ''
    modToRemove.value = null
    backupToRestore.value = null
    backupToDelete.value = null
    serverLoading.value = true
    modsLoading.value = false
    logsLoading.value = false
    backupLoading.value = false
    installLoading.value = false
    modpackInstalling.value = false
    modpackProgress.value = null
    showModpackInstallConfirmModal.value = false
    showMissingModsConfirmModal.value = false
    pendingModpackInstall.value = null
    modpackCreateBackup.value = true
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    actionState.value = { start: false, stop: false, restart: false }
    showModBrowser.value = false
    showJavaModal.value = false
    pendingJavaAction.value = null
    showModpackBrowser.value = false
    showConfirmModal.value = false
    confirmModalData.value = {}
    consoleCommand.value = ''
    commandSending.value = false
    showBackupRestoreModal.value = false
    restoringBackup.value = false
    showBackupDeleteModal.value = false
    deletingBackup.value = false
    showDeleteServerModal.value = false
    deletingServer.value = false
  }

  return {
    // State
    currentServerId,
    currentRouteName,
    serversList,
    server,
    serverLoading,
    modsLoading,
    logsLoading,
    installedMods,
    modSearch,
    logs,
    serverSettings,
    showModBrowser,
    showJavaModal,
    pendingJavaAction,
    showModpackBrowser,
    showConfirmModal,
    confirmModalData,
    modToRemove,
    installLoading,
    modpackInstalling,
    actionState,
    consoleCommand,
    commandSending,
    backups,
    backupLoading,
    fileBrowser,
    fileEditor,
    backupToRestore,
    showBackupRestoreModal,
    restoringBackup,
    backupToDelete,
    showBackupDeleteModal,
    deletingBackup,
    showDeleteServerModal,
    deletingServer,
    modpackProgress,
    showModpackInstallConfirmModal,
    pendingModpackInstall,
    modpackCreateBackup,
    showMissingModsConfirmModal,
    pendingMissingModsInstall,
    missingModsReport,
    showUncertainModsModal,
    uncertainModsReport,
    pendingUncertainModpackData,
    // Getters
    modpackProgressLabel,
    modpackProgressPercent,
    serverStatus,
    canEditSettings,
    ramMetrics,
    filteredMods,
    playersDisplay,
    statusLabel,
    startLocked,
    startButtonLabel,
    activeModpack,
    isInstalling,
    canSendCommand,
    missingModsDescriptionText,
    hasFileChanges,
    // Actions
    loadServers,
    loadServer,
    loadMods,
    loadLogs,
    loadBackups,
    refreshAll,
    createBackupAction,
    requestRestoreBackup,
    confirmRestoreBackup,
    cancelRestoreBackup,
    requestDeleteBackup,
    confirmDeleteBackup,
    cancelDeleteBackup,
    openFileBrowser,
    enterFileEntry,
    goUpDirectory,
    openFile,
    saveFile,
    closeFile,
    openModBrowser,
    openModpackBrowser,
    openDeleteServerModal,
    cancelDeleteServer,
    confirmDeleteServer,
    goToConsole,
    goToFiles,
    goToSettings,
    goToMods,
    handleInstallMod,
    handleUpdateMod,
    handleInstallModpack,
    cancelModpackInstallConfirmation,
    fetchModpackProgress,
    clearModpackProgress,
    runModpackInstall,
    confirmModpackInstall,
    cancelMissingModsConfirmation,
    confirmInstallWithMissingMods,
    cancelUncertainModsDecision,
    confirmUncertainModsDecision,
    handleRemoveMod,
    confirmRemoveMod,
    cancelRemoveMod,
    handleStart,
    handleStop,
    handleRestart,
    handleJavaInstalled,
    sendConsoleCommand,
    handleSaveSettings,
    resetSettings,
    resetState
  }
})
