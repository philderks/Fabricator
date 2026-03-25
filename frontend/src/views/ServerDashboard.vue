<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModBrowserModal from '../components/modals/ModBrowserModal.vue'
import ConfirmModal from '../components/modals/ConfirmModal.vue'
import JavaInstallModal from '../components/modals/JavaInstallModal.vue'
import ServerSettingsTab from '../components/server/ServerSettingsTab.vue'
import ServerHeader from '../components/server/ServerHeader.vue'
import ServerOverviewTab from '../components/server/ServerOverviewTab.vue'
import ServerConsoleTab from '../components/server/ServerConsoleTab.vue'
import ServerFilesTab from '../components/server/ServerFilesTab.vue'
import { installMod } from '../api/modrinth'
import {
  getServer,
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
  getJavaStatus
} from '../api/servers'
import { useToast } from '../composables/useToast'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const serverId = computed(() => route.params.id)

const server = ref(null)
const serverLoading = ref(true)
const modsLoading = ref(false)
const logsLoading = ref(false)
const installedMods = ref([])
const modSearch = ref('')
const logs = ref({ stdout: [], stderr: [], running: false })
const recentActivity = ref([])
const serverSettings = ref(null)
const showModBrowser = ref(false)
const showJavaModal = ref(false)
const javaStatus = ref({ platform: '', download_url: 'https://adoptium.net/temurin/releases/?version=21' })
const showConfirmModal = ref(false)
const confirmModalData = ref({})
const modToRemove = ref(null)
const installLoading = ref(false)
const activeTab = ref('overview')
const actionState = ref({ start: false, stop: false, restart: false })
const consoleCommand = ref('')
const commandSending = ref(false)
const backups = ref([])
const backupLoading = ref(false)
const fileBrowser = ref({ currentPath: '', entries: [], loading: false, error: null })
const backupToRestore = ref(null)
const showBackupRestoreModal = ref(false)
const restoringBackup = ref(false)
const backupToDelete = ref(null)
const showBackupDeleteModal = ref(false)
const deletingBackup = ref(false)
const showDeleteServerModal = ref(false)
const deletingServer = ref(false)
const settingsTabRef = ref(null)

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

const loadServer = async (options = {}) => {
  const { silent = false } = options
  if (!silent) {
    serverLoading.value = true
  }
  try {
    const data = await getServer(serverId.value)
    server.value = data
    const mappedSettings = defaultSettings(data)
    if (!serverSettings.value || activeTab.value !== 'settings') {
      serverSettings.value = mappedSettings
    }
  } catch (error) {
    console.error('Failed to load server:', error)
    toast.error('Could not load server details', 'Error')
  } finally {
    if (!silent) {
      serverLoading.value = false
    }
  }
}

const loadMods = async () => {
  modsLoading.value = true
  try {
    const files = await getInstalledMods(serverId.value)
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

const loadLogs = async (limit = 200) => {
  if (!server.value) {
    return
  }
  if (logsLoading.value) {
    return
  }
  logsLoading.value = true
  try {
    logs.value = await getServerLogs(serverId.value, { limit })
  } catch (error) {
    console.error('Failed to load logs:', error)
    toast.error('Failed to load console logs', 'Error')
  } finally {
    logsLoading.value = false
  }
}

const loadBackups = async () => {
  backupLoading.value = true
  try {
    backups.value = await getBackups(serverId.value)
  } catch (error) {
    console.error('Failed to load backups:', error)
    toast.error('Failed to load backups', 'Backups')
  } finally {
    backupLoading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([loadServer(), loadMods(), loadBackups()])
}

const createBackupAction = async () => {
  if (backupLoading.value) {
    return
  }
  backupLoading.value = true
  try {
    await createBackup(serverId.value)
    toast.success('Backup created successfully', 'Backups')
    await loadBackups()
    activeTab.value = 'files'
  } catch (error) {
    console.error('Failed to create backup:', error)
    toast.error(error.message || 'Failed to create backup', 'Backups')
  } finally {
    backupLoading.value = false
  }
}

const formatBackupTime = (timestamp) => {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }
  return date.toLocaleString()
}

const requestRestoreBackup = (backup) => {
  backupToRestore.value = backup
  showBackupRestoreModal.value = true
}

const confirmRestoreBackup = async () => {
  if (!backupToRestore.value) {
    return
  }
  restoringBackup.value = true
  try {
    const backupId = backupToRestore.value.relativePath.replace(/\.zip$/i, '')
    await restoreBackup(serverId.value, backupId)
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

const cancelRestoreBackup = () => {
  showBackupRestoreModal.value = false
  backupToRestore.value = null
}

const requestDeleteBackup = (backup) => {
  backupToDelete.value = backup
  showBackupDeleteModal.value = true
}

const confirmDeleteBackup = async () => {
  if (!backupToDelete.value) {
    return
  }
  deletingBackup.value = true
  try {
    const backupId = backupToDelete.value.relativePath.replace(/\.zip$/i, '')
    await deleteBackup(serverId.value, backupId)
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

const cancelDeleteBackup = () => {
  showBackupDeleteModal.value = false
  backupToDelete.value = null
}
const openFileBrowser = async (path = '') => {
  fileBrowser.value.loading = true
  fileBrowser.value.error = null
  try {
    const data = await browseServerFiles(serverId.value, path ? { path } : {})
    fileBrowser.value = { ...data, entries: data.entries, loading: false, error: null }
  } catch (error) {
    console.error('Failed to browse files:', error)
    fileBrowser.value = { currentPath: path, entries: [], loading: false, error: error.message || 'Unable to load files' }
  }
}

const enterFileEntry = (entry) => {
  if (entry.isDir) {
    openFileBrowser(entry.relativePath)
  }
}

const goUpDirectory = () => {
  if (!fileBrowser.value.currentPath) {
    return
  }
  const parts = fileBrowser.value.currentPath.split('/').filter(Boolean)
  parts.pop()
  openFileBrowser(parts.join('/'))
}

const formatFileSize = (bytes) => {
  if (!Number.isFinite(bytes)) {
    return '—'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[idx]}`
}

const scrollToSettingsSection = () => {
  activeTab.value = 'settings'
}

watch(activeTab, (tab) => {
  if (tab === 'console') {
    loadLogs()
    startLogPolling()
  } else {
    stopLogPolling()
  }

  if (tab === 'files' && !fileBrowser.value.entries.length && !fileBrowser.value.loading) {
    openFileBrowser()
  }
})

let logsIntervalId = null
let serverStatusIntervalId = null

const startLogPolling = () => {
  if (logsIntervalId || activeTab.value !== 'console') {
    return
  }
  logsIntervalId = setInterval(() => {
    loadLogs()
  }, 4000)
}

const stopLogPolling = () => {
  if (logsIntervalId) {
    clearInterval(logsIntervalId)
    logsIntervalId = null
  }
}

const startServerStatusPolling = () => {
  if (serverStatusIntervalId) {
    return
  }
  serverStatusIntervalId = setInterval(() => {
    loadServer({ silent: true })
  }, 2500)
}

const stopServerStatusPolling = () => {
  if (serverStatusIntervalId) {
    clearInterval(serverStatusIntervalId)
    serverStatusIntervalId = null
  }
}

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
  if (!Number.isFinite(total) || total <= 0) {
    total = 1
  }
  let used = 0

  if (runtimeRam) {
    if (typeof runtimeRam.usedGB === 'number') {
      used = runtimeRam.usedGB
    } else if (typeof runtimeRam.usedBytes === 'number') {
      used = runtimeRam.usedBytes / (1024 ** 3)
    } else if (typeof runtimeRam.used === 'number') {
      used = runtimeRam.used
    }
  }

  used = Math.max(0, Math.min(used, total))

  return {
    used,
    total,
    running: serverStatus.value.status === 'running'
  }
})

const filteredMods = computed(() => {
  if (!modSearch.value) {
    return installedMods.value
  }
  return installedMods.value.filter((mod) =>
    mod.name.toLowerCase().includes(modSearch.value.toLowerCase())
  )
})

const playersDisplay = computed(() => {
  const online = serverStatus.value.players.online
  const max = serverStatus.value.players.max
  return max ? `${online}/${max}` : `${online}`
})

const statusLabel = computed(() => {
  const status = serverStatus.value.status
  if (status === 'running') {
    return 'Running'
  }
  if (status === 'stopped') {
    return 'Stopped'
  }
  if (status === 'pending') {
    return 'Install Required'
  }
  if (status === 'installing') {
    return 'Installing'
  }
  if (status === 'failed') {
    return 'Failed'
  }
  return status?.charAt(0).toUpperCase() + status?.slice(1) || 'Unknown'
})

const logActivity = (entry) => {
  recentActivity.value.unshift({
    ...entry,
    time: new Date().toLocaleTimeString()
  })
  if (recentActivity.value.length > 20) {
    recentActivity.value.pop()
  }
}

const startLocked = computed(() => ['installing', 'pending'].includes(serverStatus.value.status))

const startButtonLabel = computed(() => {
  if (serverStatus.value.status === 'installing') {
    return 'Installing…'
  }
  if (serverStatus.value.status === 'pending') {
    return 'Install Required'
  }
  return actionState.value.start ? 'Starting…' : 'Start'
})

const openModBrowser = () => {
  showModBrowser.value = true
}

const openDeleteServerModal = () => {
  showDeleteServerModal.value = true
}

const cancelDeleteServer = () => {
  showDeleteServerModal.value = false
}

const confirmDeleteServer = async () => {
  deletingServer.value = true
  try {
    await deleteServer(serverId.value)
    toast.success('Server deleted', 'Servers')
    router.push('/')
  } catch (error) {
    console.error('Failed to delete server:', error)
    toast.error(error.message || 'Failed to delete server', 'Server Error')
  } finally {
    deletingServer.value = false
    showDeleteServerModal.value = false
  }
}

const handleInstallMod = async (modData) => {
  if (!server.value) {
    return
  }
  installLoading.value = true
  try {
    await installMod(modData.modId, {
      mc_version: modData.mcVersion,
      loader: modData.loader,
      server_id: serverId.value
    })
    showModBrowser.value = false
    toast.success(`${modData.modTitle} installed successfully!`, 'Mod Installed')
    logActivity({ type: 'mod_install', mod: modData.modTitle })
    await loadMods()
  } catch (error) {
    console.error('Install failed:', error)
    toast.error(error.message || 'Mod installation failed', 'Installation Failed')
  } finally {
    installLoading.value = false
  }
}

const handleUpdateMod = (mod) => {
  console.log('Update mod placeholder:', mod)
  toast.info('Mod updates coming soon', 'Not Implemented')
}

const handleRemoveMod = (mod) => {
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

const confirmRemoveMod = async () => {
  if (!modToRemove.value) {
    return
  }
  try {
    await removeMod(serverId.value, modToRemove.value.filename || modToRemove.value.name)
    toast.success(`${modToRemove.value.name} removed`, 'Mod Removed')
    logActivity({ type: 'mod_remove', mod: modToRemove.value.name })
    await loadMods()
  } catch (error) {
    console.error('Failed to remove mod:', error)
    toast.error('Failed to remove mod', 'Error')
  } finally {
    showConfirmModal.value = false
    modToRemove.value = null
  }
}

const cancelRemoveMod = () => {
  showConfirmModal.value = false
  modToRemove.value = null
}

const performServerAction = async (action, fn, successMessage) => {
  if (actionState.value[action]) {
    return
  }
  actionState.value = { ...actionState.value, [action]: true }
  try {
    const result = await fn(serverId.value)
    if (result.success) {
      toast.success(successMessage, 'Server Updated')
      logActivity({ type: `server_${action}` })
    } else {
      toast.error(result.message || 'Operation failed', 'Server Error')
    }
  } catch (error) {
    console.error(`Failed to ${action} server:`, error)
    if (error.data?.java_missing) {
      try { javaStatus.value = await getJavaStatus() } catch (_) { /* ignore */ }
      showJavaModal.value = true
    } else {
      toast.error(error.message || `Failed to ${action} server`, 'Server Error')
    }
  } finally {
    actionState.value = { ...actionState.value, [action]: false }
    await loadServer()
    if (action === 'stop') {
      stopLogPolling()
      logs.value = { stdout: [], stderr: [], running: false }
    }
    if (action === 'start' || action === 'restart') {
      await loadLogs()
      if (activeTab.value === 'console') {
        startLogPolling()
      }
    }
  }
}

const handleStart = () => performServerAction('start', startServer, 'Server start requested')
const handleStop = () => performServerAction('stop', stopServer, 'Server stop requested')
const handleRestart = () => performServerAction('restart', restartServer, 'Server restart requested')

const canSendCommand = computed(() => serverStatus.value.status === 'running' && !!server.value)

const sendConsoleCommand = async () => {
  if (!canSendCommand.value || !consoleCommand.value.trim()) {
    return
  }
  commandSending.value = true
  try {
    await sendServerCommand(serverId.value, consoleCommand.value.trim())
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

const handleSaveSettings = async (settings) => {
  if (!server.value) {
    return
  }
  try {
    const updated = await updateServerSettings(serverId.value, settings)
    server.value = updated
    serverSettings.value = defaultSettings(updated)
    toast.success('Settings saved successfully', 'Settings Updated')
    logActivity({ type: 'settings_update' })
  } catch (error) {
    console.error('Failed to save settings:', error)
    toast.error(error.message || 'Failed to save settings', 'Error')
  }
}

const resetSettings = () => {
  if (!server.value) {
    return
  }
  serverSettings.value = defaultSettings(server.value)
}

const resetDashboardState = () => {
  server.value = null
  serverSettings.value = null
  installedMods.value = []
  logs.value = { stdout: [], stderr: [], running: false }
  recentActivity.value = []
  backups.value = []
  fileBrowser.value = { currentPath: '', entries: [], loading: false, error: null }
  modSearch.value = ''
  modToRemove.value = null
  backupToRestore.value = null
  serverLoading.value = true
  modsLoading.value = false
  logsLoading.value = false
  backupLoading.value = false
  installLoading.value = false
  actionState.value = { start: false, stop: false, restart: false }
}

watch(serverId, async (newId, oldId) => {
  if (!newId || newId === oldId) {
    return
  }
  stopLogPolling()
  stopServerStatusPolling()
  resetDashboardState()
  await refreshAll()
  if (activeTab.value === 'console') {
    await loadLogs()
    startLogPolling()
  }
  startServerStatusPolling()
})

onMounted(async () => {
  await refreshAll()
  startServerStatusPolling()
})

onUnmounted(() => {
  stopLogPolling()
  stopServerStatusPolling()
})
</script>

<template>
  <div class="page">
    <ServerHeader
      :server="server"
      :server-loading="serverLoading"
      :server-status="serverStatus"
      :status-label="statusLabel"
      :action-state="actionState"
      :start-locked="startLocked"
      :start-button-label="startButtonLabel"
      :deleting-server="deletingServer"
      @start="handleStart"
      @stop="handleStop"
      @restart="handleRestart"
      @delete="openDeleteServerModal"
    />

    <main v-if="!serverLoading && server" class="main">
      <div class="content">
        <div class="tabs">
          <button 
            class="tab" 
            :class="{ active: activeTab === 'overview' }"
            @click="activeTab = 'overview'"
          >
            Overview
          </button>
          <button 
            class="tab" 
            :class="{ active: activeTab === 'console' }"
            @click="activeTab = 'console'"
          >
            Console
          </button>
          <button 
            class="tab" 
            :class="{ active: activeTab === 'files' }"
            @click="activeTab = 'files'"
          >
            Files
          </button>
          <button 
            class="tab" 
            :class="{ active: activeTab === 'settings' }"
            @click="activeTab = 'settings'"
          >
            Settings
          </button>
        </div>

        <ServerOverviewTab
          v-if="activeTab === 'overview'"
          :server-status="serverStatus"
          :players-display="playersDisplay"
          :installed-mods="installedMods"
          v-model:mod-search="modSearch"
          :mods-loading="modsLoading"
          :filtered-mods="filteredMods"
          :ram-metrics="ramMetrics"
          :recent-activity="recentActivity"
          :install-loading="installLoading"
          :backup-loading="backupLoading"
          :backups="backups"
          :format-backup-time="formatBackupTime"
          @browse-mods="openModBrowser"
          @remove-mod="handleRemoveMod"
          @update-mod="handleUpdateMod"
          @create-backup="createBackupAction"
          @open-console="activeTab = 'console'"
          @open-files="activeTab = 'files'"
          @scroll-settings="scrollToSettingsSection"
          @request-restore-backup="requestRestoreBackup"
          @request-delete-backup="requestDeleteBackup"
        />

        <ServerConsoleTab
          v-else-if="activeTab === 'console'"
          :server-status="serverStatus"
          :status-label="statusLabel"
          :logs="logs"
          :logs-loading="logsLoading"
          v-model:console-command="consoleCommand"
          :can-send-command="canSendCommand"
          :command-sending="commandSending"
          @refresh-logs="loadLogs"
          @send-command="sendConsoleCommand"
        />

        <ServerFilesTab
          v-else-if="activeTab === 'files'"
          :server-id="serverId"
          :file-browser="fileBrowser"
          :format-file-size="formatFileSize"
          @go-up="goUpDirectory"
          @refresh="openFileBrowser(fileBrowser.currentPath)"
          @enter-entry="enterFileEntry"
        />

        <ServerSettingsTab
          ref="settingsTabRef"
          v-else-if="activeTab === 'settings' && serverSettings"
          :settings="serverSettings"
          :server-version="serverStatus.version"
          :server-loader="serverStatus.loader"
          :can-edit="canEditSettings"
          @save="handleSaveSettings"
          @reset="resetSettings"
        />
      </div>
    </main>

    <div v-else-if="serverLoading" class="loading-state">
      Loading server data…
    </div>
    <div v-else class="loading-state">
      Unable to find this server.
    </div>

    <!-- Modals -->
    <ModBrowserModal 
      :show="showModBrowser"
      :mc-version="server?.version || serverStatus.version"
      :loader="(server?.loader || serverStatus.loader).toLowerCase()"
      @close="showModBrowser = false"
      @install="handleInstallMod"
    />

    <ConfirmModal
      :show="showConfirmModal"
      :title="confirmModalData.title"
      :message="confirmModalData.message"
      :description="confirmModalData.description"
      :type="confirmModalData.type"
      :confirm-text="confirmModalData.confirmText"
      :cancel-text="confirmModalData.cancelText"
      @confirm="confirmRemoveMod"
      @cancel="cancelRemoveMod"
      @close="cancelRemoveMod"
    />

    <ConfirmModal
      :show="showBackupRestoreModal"
      title="Restore Backup"
      :message="backupToRestore ? `Restore ${backupToRestore.name}?` : ''"
      description="Restoring will overwrite the current world and configs. Make sure the server is stopped."
      type="warning"
      confirm-text="Restore"
      cancel-text="Cancel"
      :loading="restoringBackup"
      @confirm="confirmRestoreBackup"
      @cancel="cancelRestoreBackup"
      @close="cancelRestoreBackup"
    />

    <ConfirmModal
      :show="showBackupDeleteModal"
      title="Delete Backup"
      :message="backupToDelete ? `Delete ${backupToDelete.name}?` : ''"
      description="This backup will be permanently deleted. This action cannot be undone."
      type="danger"
      confirm-text="Delete"
      cancel-text="Cancel"
      :loading="deletingBackup"
      @confirm="confirmDeleteBackup"
      @cancel="cancelDeleteBackup"
      @close="cancelDeleteBackup"
    />

    <ConfirmModal
      :show="showDeleteServerModal"
      title="Delete Server"
      message="Delete this server permanently?"
      description="All server files and backups will be deleted. This cannot be undone."
      type="danger"
      confirm-text="Delete"
      cancel-text="Cancel"
      :loading="deletingServer"
      @confirm="confirmDeleteServer"
      @cancel="cancelDeleteServer"
      @close="cancelDeleteServer"
    />

    <JavaInstallModal
      :show="showJavaModal"
      :platform="javaStatus.platform"
      :download-url="javaStatus.download_url"
      @close="showJavaModal = false"
    />
  </div>
</template>
