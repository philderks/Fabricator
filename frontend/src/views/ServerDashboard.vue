<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import StatCard from '../components/ui/StatCard.vue'
import PerformanceMetrics from '../components/server/PerformanceMetrics.vue'
import ModItem from '../components/server/ModItem.vue'
import ActivityFeed from '../components/server/ActivityFeed.vue'
import ModBrowserModal from '../components/modals/ModBrowserModal.vue'
import ConfirmModal from '../components/modals/ConfirmModal.vue'
import ServerSettingsTab from '../components/server/ServerSettingsTab.vue'
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
  getServerFile,
  saveServerFile,
  createBackup,
  getBackups,
  restoreBackup
} from '../api/servers'
import { useToast } from '../composables/useToast'

const route = useRoute()
const toast = useToast()
const serverId = route.params.id

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

const defaultSettings = (data = {}) => ({
  name: data.name || 'Minecraft Server',
  port: data.port || 25565,
  motd: data.motd || 'A Minecraft Server',
  maxPlayers: data.maxPlayers ?? 20,
  difficulty: data.difficulty || 'normal',
  gamemode: data.gamemode || 'survival',
  viewDistance: data.viewDistance ?? 10,
  levelName: data.levelName || 'world',
  levelType: data.levelType || 'default',
  seed: data.seed || '',
  generateStructures: data.generateStructures ?? true,
  spawnAnimals: data.spawnAnimals ?? true,
  spawnMonsters: data.spawnMonsters ?? true,
  spawnNpcs: data.spawnNpcs ?? true,
  memory: data.memory ?? 4,
  simulationDistance: data.simulationDistance ?? 10,
  onlineMode: data.onlineMode ?? true,
  whitelist: data.whitelist ?? false,
  pvp: data.pvp ?? true,
  commandBlocks: data.commandBlocks ?? true
})

const loadServer = async () => {
  serverLoading.value = true
  try {
    const data = await getServer(serverId)
    server.value = data
    serverSettings.value = defaultSettings(data)
  } catch (error) {
    console.error('Failed to load server:', error)
    toast.error('Could not load server details', 'Error')
  } finally {
    serverLoading.value = false
  }
}

const loadMods = async () => {
  modsLoading.value = true
  try {
    const files = await getInstalledMods(serverId)
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
    logs.value = await getServerLogs(serverId, { limit })
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
    backups.value = await getBackups(serverId)
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
    await createBackup(serverId)
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
    await restoreBackup(serverId, backupId)
    toast.success('Backup restored successfully', 'Backups')
    await openFileBrowser()
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
const openFileBrowser = async (path = '') => {
  fileBrowser.value.loading = true
  fileBrowser.value.error = null
  try {
    const data = await browseServerFiles(serverId, path ? { path } : {})
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

const openServerProperties = async () => {
  try {
    const file = await getServerFile(serverId, 'server.properties')
    console.log(file.content)
    toast.info('server.properties loaded in console log (UI editor coming soon)', 'Files')
  } catch (error) {
    console.error('Failed to load server.properties:', error)
    toast.error('Failed to load server.properties', 'Files')
  }
}

const scrollToSettingsSection = (selector) => {
  const section = document.querySelector(`[data-settings-section="${selector}"]`)
  if (section) {
    section.scrollIntoView({ behavior: 'smooth' })
  }
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

const ramMetrics = computed(() => {
  const configuredTotal = Number(server.value?.memory ?? serverSettings.value?.memory ?? 0)
  const total = configuredTotal > 0 ? configuredTotal : 1
  const runtimeRam = server.value?.runtime?.ram
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

const handleInstallMod = async (modData) => {
  if (!server.value) {
    return
  }
  installLoading.value = true
  try {
    await installMod(modData.modId, {
      mc_version: modData.mcVersion,
      loader: modData.loader,
      server_id: serverId
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
    await removeMod(serverId, modToRemove.value.filename || modToRemove.value.name)
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
    const result = await fn(serverId)
    if (result.success) {
      toast.success(successMessage, 'Server Updated')
      logActivity({ type: `server_${action}` })
    } else {
      toast.error(result.message || 'Operation failed', 'Server Error')
    }
  } catch (error) {
    console.error(`Failed to ${action} server:`, error)
    toast.error(`Failed to ${action} server`, 'Server Error')
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
    await sendServerCommand(serverId, consoleCommand.value.trim())
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
    const updated = await updateServerSettings(serverId, settings)
    server.value = updated
    serverSettings.value = defaultSettings(updated)
    toast.success('Settings saved successfully', 'Settings Updated')
    logActivity({ type: 'settings_update' })
  } catch (error) {
    console.error('Failed to save settings:', error)
    toast.error('Failed to save settings', 'Error')
  }
}

const resetSettings = () => {
  if (!server.value) {
    return
  }
  serverSettings.value = defaultSettings(server.value)
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

onMounted(async () => {
  await refreshAll()
})

onUnmounted(() => {
  stopLogPolling()
})
</script>

<template>
  <div class="page">
    <header class="header">
      <div class="header-content" v-if="!serverLoading && server">
        <div class="brand">
          <router-link to="/" class="back-btn">←</router-link>
          <div>
            <h1 class="server-title">{{ serverStatus.name }}</h1>
            <div class="server-meta">
              <span class="status-indicator" :class="serverStatus.status"></span>
              <span class="status-text">{{ statusLabel }}</span>
              <span class="separator">•</span>
              <span>{{ serverStatus.loader }} {{ serverStatus.version }}</span>
            </div>
          </div>
        </div>
        <div class="server-controls">
          <button
            class="btn btn-danger"
            v-if="serverStatus.status === 'running'"
            :disabled="actionState.stop"
            @click="handleStop"
          >
            {{ actionState.stop ? 'Stopping…' : 'Stop' }}
          </button>
          <button
            class="btn btn-success"
            v-else
            :disabled="actionState.start || startLocked"
            @click="handleStart"
          >
            {{ startButtonLabel }}
          </button>
          <button
            class="btn btn-secondary"
            :disabled="actionState.restart || serverStatus.status !== 'running'"
            @click="handleRestart"
          >
            {{ actionState.restart ? 'Restarting…' : 'Restart' }}
          </button>
        </div>
      </div>
      <div class="header-content" v-else>
        <div class="brand">
          <router-link to="/" class="back-btn">←</router-link>
          <div>
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-subtitle"></div>
          </div>
        </div>
      </div>
    </header>

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

        <!-- Overview Tab -->
        <div v-if="activeTab === 'overview'" class="grid">
          <!-- Stats Overview -->
          <div class="stats-row">
            <StatCard 
              label="Players Online" 
              :value="playersDisplay"
            />
            <StatCard label="Uptime" :value="serverStatus.uptime" />
            <StatCard label="TPS" :value="serverStatus.tps" />
            <StatCard label="Mods" :value="installedMods.length" />
          </div>

          <div class="two-col">
            <!-- Left Column -->
            <div class="col">
              <!-- Performance -->
              <div class="card">
                <div class="card-header">
                  <h3>Performance</h3>
                </div>
                <PerformanceMetrics :ram="ramMetrics" />
              </div>

              <!-- Recent Activity -->
              <div class="card">
                <div class="card-header">
                  <h3>Recent Activity</h3>
                  <button class="btn-text">View All</button>
                </div>
                <ActivityFeed :activities="recentActivity" />
              </div>
            </div>

            <!-- Right Column -->
            <div class="col">
              <!-- Installed Mods -->
              <div class="card">
                <div class="card-header">
                  <h3>Installed Mods ({{ installedMods.length }})</h3>
                  <button class="btn btn-primary" :disabled="installLoading" @click="openModBrowser">
                    {{ installLoading ? 'Installing…' : 'Browse Mods' }}
                  </button>
                </div>
                <div class="search-box">
                  <input
                    v-model="modSearch"
                    type="text"
                    placeholder="Search mods..."
                    class="search-input"
                    :disabled="modsLoading"
                  >
                </div>
                <div v-if="modsLoading" class="mods-state">Loading mods…</div>
                <div v-else-if="!filteredMods.length" class="mods-state">No mods installed yet.</div>
                <div v-else class="mods-list">
                  <ModItem
                    v-for="mod in filteredMods"
                    :key="mod.filename || mod.name"
                    :mod="mod"
                    @update="handleUpdateMod"
                    @remove="handleRemoveMod"
                  />
                </div>
              </div>

              <!-- Quick Actions -->
              <div class="card">
                <div class="card-header">
                  <h3>Quick Actions</h3>
                </div>
                <div class="action-grid">
                  <button class="action-card" :disabled="backupLoading" @click="createBackupAction">
                    <div class="action-label">Backup Server</div>
                    <div class="action-desc">{{ backupLoading ? 'Creating…' : 'Create full backup' }}</div>
                  </button>
                  <button class="action-card" @click="activeTab = 'console'">
                    <div class="action-label">View Logs</div>
                    <div class="action-desc">Jump to console</div>
                  </button>
                  <button class="action-card" @click="openServerProperties">
                    <div class="action-label">Server Properties</div>
                    <div class="action-desc">Edit server.properties</div>
                  </button>
                  <button class="action-card" @click="scrollToSettingsSection('world')">
                    <div class="action-label">World Settings</div>
                    <div class="action-desc">Go to world config</div>
                  </button>
                </div>
              </div>

              <div class="card">
                <div class="card-header">
                  <h3>Backups</h3>
                  <button class="btn-text" @click="activeTab = 'files'">Open folder</button>
                </div>
                <div v-if="backupLoading" class="mods-state">Loading backups…</div>
                <div v-else-if="!backups.length" class="mods-state">No backups yet. Create one to get started.</div>
                <div v-else class="backups-list">
                  <div class="backup-item" v-for="backup in backups" :key="backup.relativePath">
                    <div>
                      <div class="backup-name">{{ backup.name }}</div>
                      <div class="backup-meta">{{ formatBackupTime(backup.updatedAt) }}</div>
                    </div>
                    <div class="backup-actions">
                      <button class="btn-text" @click="requestRestoreBackup(backup)">Restore</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Console Tab -->
        <div v-else-if="activeTab === 'console'" class="console-tab">
          <div class="console-toolbar">
            <div class="status-pill" :class="serverStatus.status">
              Server {{ statusLabel }}
            </div>
            <button class="btn btn-secondary" :disabled="logsLoading" @click="loadLogs">
              {{ logsLoading ? 'Refreshing…' : 'Refresh Logs' }}
            </button>
          </div>
          <div class="console-command">
            <input
              v-model="consoleCommand"
              class="command-input"
              type="text"
              placeholder="Enter server command (e.g., say Hello)"
              :disabled="!canSendCommand || commandSending"
              @keyup.enter="sendConsoleCommand"
            >
            <button
              class="btn btn-primary"
              :disabled="!canSendCommand || commandSending || !consoleCommand.trim()"
              @click="sendConsoleCommand"
            >
              {{ commandSending ? 'Sending…' : 'Send Command' }}
            </button>
          </div>
          <p class="command-hint" v-if="!canSendCommand">
            Server must be running to accept console commands.
          </p>
          <div class="console-output">
            <div class="console-stream">
              <div class="console-stream__header">STDOUT</div>
              <div class="console-stream__body">
                <template v-if="logs.stdout?.length">
                  <pre v-for="(line, idx) in logs.stdout" :key="`stdout-${idx}`">{{ line }}</pre>
                </template>
                <p v-else class="console-empty">No output yet.</p>
              </div>
            </div>
            <div class="console-stream">
              <div class="console-stream__header">STDERR</div>
              <div class="console-stream__body">
                <template v-if="logs.stderr?.length">
                  <pre v-for="(line, idx) in logs.stderr" :key="`stderr-${idx}`">{{ line }}</pre>
                </template>
                <p v-else class="console-empty">No errors reported.</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Files Tab -->
        <div v-else-if="activeTab === 'files'" class="files-tab">
          <div class="files-toolbar">
            <div class="files-toolbar-left">
              <button class="btn btn-secondary" :disabled="!fileBrowser.currentPath" @click="goUpDirectory">
                Up
              </button>
              <button class="btn btn-secondary" @click="openFileBrowser(fileBrowser.currentPath)">
                Refresh
              </button>
            </div>
            <div class="path-display">/{{ fileBrowser.currentPath }}</div>
          </div>
          <div class="files-list" v-if="!fileBrowser.loading && !fileBrowser.error">
            <div
              v-for="entry in fileBrowser.entries"
              :key="entry.path"
              class="file-entry"
              @click="enterFileEntry(entry)"
            >
              <div class="file-info">
                <span class="file-name">{{ entry.relativePath }}</span>
                <span class="file-meta">{{ entry.isDir ? 'Folder' : formatFileSize(entry.size) }}</span>
              </div>
            </div>
          </div>
          <div v-else-if="fileBrowser.loading" class="placeholder-state">
            <p>Loading files…</p>
          </div>
          <div v-else class="placeholder-state">
            <p>{{ fileBrowser.error }}</p>
          </div>
        </div>

        <!-- Settings Tab -->
        <ServerSettingsTab
          v-else-if="activeTab === 'settings' && serverSettings"
          :settings="serverSettings"
          :server-version="serverStatus.version"
          :server-loader="serverStatus.loader"
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
  </div>
</template>

<style scoped>
/* Component-specific styles only */
/* Header specific */
.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 1.25rem;
  transition: all 0.2s;
}

.back-btn:hover {
  background: var(--primary);
  color: white;
}

.server-title {
  margin: 0 0 0.375rem 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.server-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.running {
  background: var(--success);
}

.status-indicator.stopped {
  background: var(--text-disabled);
}

.status-indicator.pending,
.status-indicator.installing {
  background: #fbbf24;
}

.status-indicator.failed {
  background: #ef4444;
}

.status-text {
  font-weight: 500;
}

.separator {
  color: var(--text-disabled);
}

.server-controls {
  display: flex;
  gap: 0.75rem;
}

/* Column layout */
.col {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Search box */
.search-box {
  margin-bottom: 1rem;
}

.search-input {
  width: 100%;
  padding: 0.625rem 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: var(--primary);
}

.search-input::placeholder {
  color: var(--text-disabled);
}

/* Mods list */
.mods-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 400px;
  overflow-y: auto;
}

.backups-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.backup-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
}

.backup-name {
  font-weight: 600;
  color: var(--text-primary);
}

.backup-meta {
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.backup-actions {
  display: flex;
  gap: 0.5rem;
}

/* Settings list */
.settings-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.setting-label {
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 500;
}

.setting-value {
  color: var(--text-primary);
  font-weight: 600;
}

/* Quick actions */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.action-card {
  padding: 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}

.action-card:hover {
  border-color: var(--primary);
  background: var(--bg-secondary);
}

.action-label {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 0.875rem;
  margin-bottom: 0.25rem;
}

.action-desc {
  color: var(--text-disabled);
  font-size: 0.8125rem;
}

/* Placeholder */
.tab-content {
  padding: 4rem 2rem;
}

.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 4rem 2rem;
  color: var(--text-muted);
}

.placeholder-state svg {
  color: var(--text-disabled);
  margin-bottom: 1.5rem;
}

.placeholder-state h3 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 0.5rem 0;
}

.placeholder-state p {
  font-size: 1rem;
  margin: 0;
}

.mods-state {
  padding: 1rem;
  text-align: center;
  color: var(--text-muted);
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.loading-state {
  padding: 4rem 2rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 1rem;
}

.skeleton {
  background: linear-gradient(90deg, var(--bg-tertiary), var(--bg-secondary), var(--bg-tertiary));
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}

.skeleton-title {
  width: 180px;
  height: 24px;
  margin-bottom: 0.5rem;
}

.skeleton-subtitle {
  width: 140px;
  height: 16px;
}

.console-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.console-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.console-command {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.command-input {
  flex: 1;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
}

.command-input:focus {
  outline: none;
  border-color: var(--primary);
}

.command-hint {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.status-pill {
  padding: 0.375rem 0.75rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: white;
}

.status-pill.running {
  background: var(--success);
}

.status-pill.stopped {
  background: var(--text-disabled);
}

.status-pill.pending {
  background: #fbbf24;
}

.status-pill.installing {
  background: #fbbf24;
}

.status-pill.failed {
  background: #ef4444;
}

.console-output {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.console-stream__header {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.console-stream__body {
  background: black;
  color: #e5e7eb;
  padding: 1rem;
  border-radius: 8px;
  min-height: 240px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.console-stream__body pre {
  margin: 0;
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
  font-size: 0.875rem;
  line-height: 1.4;
  white-space: pre-wrap;
}

.console-empty {
  margin: 0;
  color: #94a3b8;
}

.files-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.files-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.files-toolbar-left {
  display: flex;
  gap: 0.5rem;
}

.path-display {
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
  color: var(--text-muted);
}

.files-list {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.file-entry {
  display: flex;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: background 0.2s;
}

.file-entry:last-child {
  border-bottom: none;
}

.file-entry:hover {
  background: var(--bg-tertiary);
}

.file-name {
  font-weight: 600;
}

.file-meta {
  font-size: 0.8125rem;
  color: var(--text-disabled);
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 768px) {
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
