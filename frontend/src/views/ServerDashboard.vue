<script setup>
import { computed, onMounted, ref, watch } from 'vue'
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
  updateServerSettings
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

const refreshAll = async () => {
  await Promise.all([loadServer(), loadMods()])
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
    cpu: server.value?.runtime?.cpu ?? 0,
    ram: server.value?.runtime?.ram || { used: 0, total: server.value?.memory ?? 0 },
    tps: server.value?.runtime?.tps ?? 20
  }
})

const ramMetrics = computed(() => {
  const runtimeRam = server.value?.runtime?.ram
  const defaultTotal = server.value?.memory ?? 4

  if (runtimeRam && typeof runtimeRam.used === 'number' && typeof runtimeRam.total === 'number') {
    const total = runtimeRam.total || defaultTotal || 1
    const used = Math.min(runtimeRam.used, total)
    return { used, total }
  }

  return {
    used: 0,
    total: defaultTotal || 1
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
      logs.value = { stdout: [], stderr: [], running: false }
    }
    if (action === 'start' || action === 'restart') {
      await loadLogs()
    }
  }
}

const handleStart = () => performServerAction('start', startServer, 'Server start requested')
const handleStop = () => performServerAction('stop', stopServer, 'Server stop requested')
const handleRestart = () => performServerAction('restart', restartServer, 'Server restart requested')

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
  }
})

onMounted(async () => {
  await refreshAll()
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
                <PerformanceMetrics :cpu="serverStatus.cpu" :ram="ramMetrics" />
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
                  <button class="action-card">
                    <div class="action-label">Backup Server</div>
                    <div class="action-desc">Create a backup</div>
                  </button>
                  <button class="action-card">
                    <div class="action-label">View Logs</div>
                    <div class="action-desc">Check server logs</div>
                  </button>
                  <button class="action-card">
                    <div class="action-label">Server Properties</div>
                    <div class="action-desc">Edit server.properties</div>
                  </button>
                  <button class="action-card">
                    <div class="action-label">World Settings</div>
                    <div class="action-desc">Configure world</div>
                  </button>
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
        <div v-else-if="activeTab === 'files'" class="tab-content">
          <div class="placeholder-state">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
              <path d="M13 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V9L13 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M13 2V9H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <h3>File Browser</h3>
            <p>Server file management will be available here</p>
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
