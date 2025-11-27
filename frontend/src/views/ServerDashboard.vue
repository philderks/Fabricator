<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import StatCard from '../components/StatCard.vue'
import PerformanceMetrics from '../components/PerformanceMetrics.vue'
import ModItem from '../components/ModItem.vue'
import ActivityFeed from '../components/ActivityFeed.vue'

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

const handleUpdateMod = (mod) => {
  console.log('Update mod:', mod)
}

const handleRemoveMod = (mod) => {
  console.log('Remove mod:', mod)
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
          <button class="tab active">Overview</button>
          <button class="tab">Console</button>
          <button class="tab">Files</button>
          <button class="tab">Settings</button>
        </div>

        <div class="grid">
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

              <!-- Server Settings -->
              <div class="card">
                <div class="card-header">
                  <h3>Server Configuration</h3>
                  <button class="btn-text">Edit</button>
                </div>
                <div class="settings-list">
                  <div class="setting-item">
                    <div class="setting-label">Server Name</div>
                    <div class="setting-value">{{ serverStatus.name }}</div>
                  </div>
                  <div class="setting-item">
                    <div class="setting-label">Version</div>
                    <div class="setting-value">{{ serverStatus.version }}</div>
                  </div>
                  <div class="setting-item">
                    <div class="setting-label">Loader</div>
                    <div class="setting-value">{{ serverStatus.loader }}</div>
                  </div>
                  <div class="setting-item">
                    <div class="setting-label">Max Players</div>
                    <div class="setting-value">{{ serverStatus.players.max }}</div>
                  </div>
                  <div class="setting-item">
                    <div class="setting-label">Difficulty</div>
                    <div class="setting-value">Normal</div>
                  </div>
                  <div class="setting-item">
                    <div class="setting-label">Game Mode</div>
                    <div class="setting-value">Survival</div>
                  </div>
                </div>
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
                  <button class="btn btn-primary">Browse Mods</button>
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
      </div>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  background: #0f172a;
  color: #e2e8f0;
}

/* Header */
.header {
  background: #1e293b;
  border-bottom: 1px solid #334155;
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.5rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #334155;
  color: #e2e8f0;
  text-decoration: none;
  font-size: 1.25rem;
  transition: all 0.2s;
}

.back-btn:hover {
  background: #3b82f6;
  color: white;
}

.server-title {
  margin: 0 0 0.375rem 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #f1f5f9;
}

.server-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #94a3b8;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.running {
  background: #10b981;
}

.status-indicator.stopped {
  background: #64748b;
}

.status-text {
  font-weight: 500;
}

.separator {
  color: #64748b;
}

.server-controls {
  display: flex;
  gap: 0.75rem;
}

/* Buttons */
.btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-success {
  background: #10b981;
  color: white;
}

.btn-success:hover {
  background: #059669;
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}

.btn-secondary {
  background: #334155;
  color: #e2e8f0;
}

.btn-secondary:hover {
  background: #475569;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-text {
  background: transparent;
  border: none;
  color: #3b82f6;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
}

.btn-text:hover {
  color: #2563eb;
}

.btn-text.danger {
  color: #ef4444;
}

.btn-text.danger:hover {
  color: #dc2626;
}

/* Main */
.main {
  max-width: 1400px;
  margin: 0 auto;
}

.content {
  padding: 2rem;
}

.grid {
  display: grid;
  gap: 1.5rem;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 2rem;
  border-bottom: 1px solid #334155;
  padding-bottom: 0;
}

.tab {
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  color: #94a3b8;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab:hover {
  color: #e2e8f0;
}

.tab.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

/* Two Column Layout */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

.col {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
}

/* Card */
.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 1.5rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.card-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #f1f5f9;
}

/* Mods */
.search-box {
  margin-bottom: 1rem;
}

.search-input {
  width: 100%;
  padding: 0.625rem 1rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: #3b82f6;
}

.search-input::placeholder {
  color: #64748b;
}

.mods-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 400px;
  overflow-y: auto;
}

/* Settings */
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
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
}

.setting-label {
  color: #94a3b8;
  font-size: 0.875rem;
  font-weight: 500;
}

.setting-value {
  color: #f1f5f9;
  font-weight: 600;
}

/* Quick Actions */
.action-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.action-card {
  padding: 1rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}

.action-card:hover {
  border-color: #3b82f6;
  background: #1e293b;
}

.action-label {
  color: #f1f5f9;
  font-weight: 600;
  font-size: 0.875rem;
  margin-bottom: 0.25rem;
}

.action-desc {
  color: #64748b;
  font-size: 0.8125rem;
}

@media (max-width: 1024px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .two-col {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }

  .tabs {
    overflow-x: auto;
  }

  .stats-row {
    grid-template-columns: 1fr;
  }

  .action-grid {
    grid-template-columns: 1fr;
  }

}
</style>
