<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import StatCard from '../components/ui/StatCard.vue'
import PerformanceMetrics from '../components/server/PerformanceMetrics.vue'
import ModItem from '../components/server/ModItem.vue'
import ActivityFeed from '../components/server/ActivityFeed.vue'
import ModBrowserModal from '../components/modals/ModBrowserModal.vue'
import ConfirmModal from '../components/modals/ConfirmModal.vue'
import ServerSettingsTab from '../components/server/ServerSettingsTab.vue'
import { installMod } from '../api/modrinth'

const route = useRoute()
const serverId = route.params.id

const serverStatus = ref({
  name: 'Main Survival',
  status: 'running',
  uptime: '5d 12h 34m',
  version: '1.21.3',
  loader: 'Fabric',
  players: { online: 12, max: 50 },
  cpu: 45,
  ram: { used: 2.4, total: 4 },
  tps: 19.8
})

const installedMods = ref([
  { name: 'Sodium', version: '0.6.0-beta.2', downloads: '15M', category: 'Performance' },
  { name: 'Lithium', version: '0.13.0', downloads: '8M', category: 'Performance' },
  { name: 'Iris Shaders', version: '1.8.0', downloads: '12M', category: 'Graphics' },
  { name: 'Fabric API', version: '0.95.4', downloads: '50M', category: 'Library' },
  { name: 'Mod Menu', version: '9.2.0', downloads: '20M', category: 'Utility' }
])

const recentActivity = ref([
  { type: 'player_join', user: 'Steve', time: '2m ago' },
  { type: 'mod_install', mod: 'Sodium', time: '1h ago' },
  { type: 'server_start', time: '2h ago' },
  { type: 'player_leave', user: 'Alex', time: '3h ago' },
  { type: 'mod_update', mod: 'Fabric API', time: '5h ago' }
])

// Server settings for Settings tab
const serverSettings = ref({
  // Basic
  name: 'Main Survival',
  port: 25565,
  motd: 'A Minecraft Server',
  
  // Gameplay
  maxPlayers: 50,
  difficulty: 'normal',
  gamemode: 'survival',
  viewDistance: 10,
  
  // World
  levelName: 'world',
  levelType: 'default',
  seed: '',
  generateStructures: true,
  spawnAnimals: true,
  spawnMonsters: true,
  spawnNpcs: true,
  
  // Performance
  memory: 4,
  simulationDistance: 10,
  
  // Advanced
  onlineMode: true,
  whitelist: false,
  pvp: true,
  commandBlocks: true
})

// Modal state
const showModBrowser = ref(false)
const showConfirmModal = ref(false)
const confirmModalData = ref({})
const modToRemove = ref(null)
const installLoading = ref(false)

// Tab state
const activeTab = ref('overview')

// Mod Browser
const openModBrowser = () => {
  showModBrowser.value = true
}

const handleInstallMod = async (modData) => {
  installLoading.value = true
  
  try {
    const result = await installMod(modData.modId, {
      mc_version: modData.mcVersion,
      loader: modData.loader
    })
    
    // Add to installed mods list
    installedMods.value.push({
      name: modData.modTitle,
      version: 'Latest',
      downloads: 'N/A',
      category: 'Installed'
    })
    
    // Add to activity feed
    recentActivity.value.unshift({
      type: 'mod_install',
      mod: modData.modTitle,
      time: 'just now'
    })
    
    showModBrowser.value = false
    
    // Show success notification (could be improved with a toast component)
    alert(`${modData.modTitle} installed successfully!`)
  } catch (error) {
    console.error('Install failed:', error)
    alert(`Installation failed: ${error.message}`)
  } finally {
    installLoading.value = false
  }
}

// Mod Management
const handleUpdateMod = (mod) => {
  console.log('Update mod:', mod)
  // Future: Check for updates and install
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
  if (!modToRemove.value) return
  
  // Simulate removal (replace with actual API call when available)
  installedMods.value = installedMods.value.filter(m => m.name !== modToRemove.value.name)
  
  // Add to activity feed
  recentActivity.value.unshift({
    type: 'mod_remove',
    mod: modToRemove.value.name,
    time: 'just now'
  })
  
  showConfirmModal.value = false
  modToRemove.value = null
}

const cancelRemoveMod = () => {
  showConfirmModal.value = false
  modToRemove.value = null
}

// Settings Tab
const handleSaveSettings = (settings) => {
  // Update server status with new settings
  serverStatus.value = {
    ...serverStatus.value,
    name: settings.name,
    players: {
      ...serverStatus.value.players,
      max: settings.maxPlayers
    }
  }
  
  // Update local settings
  serverSettings.value = { ...settings }
  
  // Add to activity feed
  recentActivity.value.unshift({
    type: 'settings_update',
    time: 'just now'
  })
  
  console.log('Settings saved:', settings)
  alert('Settings saved successfully!')
}

const resetSettings = () => {
  // Reload original settings (in real app, fetch from API)
  serverSettings.value = {
    name: serverStatus.value.name,
    port: 25565,
    motd: 'A Minecraft Server',
    maxPlayers: serverStatus.value.players.max,
    difficulty: 'normal',
    gamemode: 'survival',
    viewDistance: 10,
    levelName: 'world',
    levelType: 'default',
    seed: '',
    generateStructures: true,
    spawnAnimals: true,
    spawnMonsters: true,
    spawnNpcs: true,
    memory: 4,
    simulationDistance: 10,
    onlineMode: true,
    whitelist: false,
    pvp: true,
    commandBlocks: true
  }
}
</script>

<template>
  <div class="page">
    <header class="header">
      <div class="header-content">
        <div class="brand">
          <router-link to="/" class="back-btn">←</router-link>
          <div>
            <h1 class="server-title">{{ serverStatus.name }}</h1>
            <div class="server-meta">
              <span class="status-indicator" :class="serverStatus.status"></span>
              <span class="status-text">{{ serverStatus.status === 'running' ? 'Running' : 'Stopped' }}</span>
              <span class="separator">•</span>
              <span>{{ serverStatus.loader }} {{ serverStatus.version }}</span>
            </div>
          </div>
        </div>
        <div class="server-controls">
          <button class="btn btn-danger" v-if="serverStatus.status === 'running'">Stop</button>
          <button class="btn btn-success" v-else>Start</button>
          <button class="btn btn-secondary">Restart</button>
        </div>
      </div>
    </header>

    <main class="main">
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
              :value="`${serverStatus.players.online}/${serverStatus.players.max}`" 
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
                <PerformanceMetrics :cpu="serverStatus.cpu" :ram="serverStatus.ram" />
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
                  <button class="btn btn-primary" @click="openModBrowser">Browse Mods</button>
                </div>
                <div class="search-box">
                  <input type="text" placeholder="Search mods..." class="search-input">
                </div>
                <div class="mods-list">
                  <ModItem 
                    v-for="mod in installedMods" 
                    :key="mod.name" 
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
        <div v-else-if="activeTab === 'console'" class="tab-content">
          <div class="placeholder-state">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
              <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M7 10L10 13L7 16M12 16H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <h3>Console</h3>
            <p>Server console will be available here</p>
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
          v-else-if="activeTab === 'settings'"
          :settings="serverSettings"
          :server-version="serverStatus.version"
          :server-loader="serverStatus.loader"
          @save="handleSaveSettings"
          @reset="resetSettings"
        />
      </div>
    </main>

    <!-- Modals -->
    <ModBrowserModal 
      :show="showModBrowser"
      :mc-version="serverStatus.version"
      :loader="serverStatus.loader.toLowerCase()"
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

@media (max-width: 768px) {
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
