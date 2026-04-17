<script setup>
import { computed } from 'vue'
import StatCard from '../ui/StatCard.vue'
import PerformanceMetrics from './PerformanceMetrics.vue'
import ActivityFeed from './ActivityFeed.vue'
import ModItem from './ModItem.vue'

const props = defineProps({
  serverStatus: {
    type: Object,
    required: true
  },
  playersDisplay: {
    type: String,
    required: true
  },
  installedMods: {
    type: Array,
    default: () => []
  },
  activeModpack: {
    type: Object,
    default: null
  },
  modSearch: {
    type: String,
    default: ''
  },
  modsLoading: {
    type: Boolean,
    default: false
  },
  filteredMods: {
    type: Array,
    default: () => []
  },
  ramMetrics: {
    type: Object,
    required: true
  },
  recentActivity: {
    type: Array,
    default: () => []
  },
  installLoading: {
    type: Boolean,
    default: false
  },
  backupLoading: {
    type: Boolean,
    default: false
  },
  backups: {
    type: Array,
    default: () => []
  },
  formatBackupTime: {
    type: Function,
    required: true
  }
})

const emit = defineEmits([
  'update:modSearch',
  'browse-mods',
  'browse-modpacks',
  'remove-mod',
  'update-mod',
  'create-backup',
  'open-console',
  'open-files',
  'scroll-settings',
  'request-restore-backup',
  'request-delete-backup'
])

const modSearchModel = computed({
  get: () => props.modSearch,
  set: (value) => emit('update:modSearch', value)
})

const handleBrowseMods = () => emit('browse-mods')
const handleBrowseModpacks = () => emit('browse-modpacks')
const handleCreateBackup = () => emit('create-backup')
const handleOpenConsole = () => emit('open-console')
const handleOpenFiles = () => emit('open-files')
const handleScrollSettings = (section) => emit('scroll-settings', section)
const handleRequestRestore = (backup) => emit('request-restore-backup', backup)
const handleRequestDelete = (backup) => emit('request-delete-backup', backup)
</script>

<template>
  <div class="grid">
    <div class="stats-row">
      <StatCard label="Players Online" :value="playersDisplay" />
      <StatCard label="Uptime" :value="serverStatus.uptime" />
      <StatCard label="TPS" :value="serverStatus.tps" />
      <StatCard label="Mods" :value="installedMods.length" />
    </div>

    <div v-if="activeModpack" class="modpack-info">
      <div class="modpack-info__icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
      </div>
      <div class="modpack-info__details">
        <span class="modpack-info__name">{{ activeModpack.name || activeModpack.projectId }}</span>
        <span class="modpack-info__meta">
          <span v-if="activeModpack.version">{{ activeModpack.version }}</span>
          <span v-if="activeModpack.mcVersion" class="modpack-info__sep">MC {{ activeModpack.mcVersion }}</span>
          <span v-if="activeModpack.installedAt" class="modpack-info__sep">
            installed {{ new Date(activeModpack.installedAt).toLocaleDateString() }}
          </span>
        </span>
      </div>
      <button class="btn-text" :disabled="installLoading" @click="handleBrowseModpacks">
        Change
      </button>
    </div>

    <div class="two-col">
      <div class="col">
        <div class="card">
          <div class="card-header">
            <h3>Performance</h3>
          </div>
          <PerformanceMetrics :ram="ramMetrics" />
        </div>

        <div class="card">
          <div class="card-header">
            <h3>Recent Activity</h3>
            <button class="btn-text">View All</button>
          </div>
          <ActivityFeed :activities="recentActivity" />
        </div>
      </div>

      <div class="col">
        <div class="card">
          <div class="card-header">
            <h3>Installed Mods ({{ installedMods.length }})</h3>
            <div class="mod-actions">
              <button class="btn btn-secondary" :disabled="installLoading" @click="handleBrowseModpacks">
                Browse Modpacks
              </button>
              <button class="btn btn-primary" :disabled="installLoading" @click="handleBrowseMods">
                {{ installLoading ? 'Installing…' : 'Browse Mods' }}
              </button>
            </div>
          </div>
          <div class="search-box">
            <input
              v-model="modSearchModel"
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
              @update="$emit('update-mod', mod)"
              @remove="$emit('remove-mod', mod)"
            />
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3>Quick Actions</h3>
          </div>
          <div class="action-grid">
            <button class="action-card" :disabled="backupLoading" @click="handleCreateBackup">
              <div class="action-label">Backup Server</div>
              <div class="action-desc">{{ backupLoading ? 'Creating…' : 'Create full backup' }}</div>
            </button>
            <button class="action-card" @click="handleOpenConsole">
              <div class="action-label">View Logs</div>
              <div class="action-desc">Jump to console</div>
            </button>
            <button class="action-card" @click="handleScrollSettings('advanced')">
              <div class="action-label">Server Properties</div>
              <div class="action-desc">Edit server.properties</div>
            </button>
            <button class="action-card" @click="handleScrollSettings('world')">
              <div class="action-label">World Settings</div>
              <div class="action-desc">Go to world config</div>
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3>Backups</h3>
              <button class="btn-text" @click="handleOpenFiles">Open folder</button>
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
                <button class="btn-text" @click="handleRequestRestore(backup)">Restore</button>
                <button class="btn-text danger" @click="handleRequestDelete(backup)">Delete</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modpack-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.85rem;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  margin-bottom: 1.5rem;
}

.modpack-info__icon {
  color: var(--text-muted);
  flex-shrink: 0;
  display: flex;
}

.modpack-info__details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.modpack-info__name {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modpack-info__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.modpack-info__sep::before {
  content: '\00b7';
  margin-right: 0.25rem;
}

.col {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

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

.mods-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 400px;
  overflow-y: auto;
}

.mods-state {
  padding: 1rem;
  text-align: center;
  color: var(--text-muted);
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
}

.mod-actions {
  display: inline-flex;
  gap: 0.5rem;
  flex-wrap: wrap;
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
  background: var(--bg-tertiary);
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

@media (max-width: 768px) {
  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
