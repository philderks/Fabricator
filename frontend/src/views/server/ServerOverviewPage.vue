<script setup>
import { computed } from 'vue'
import StatCard from '../../components/ui/StatCard.vue'
import Panel from '../../components/ui/Panel.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const RECENT_LOG_PREVIEW_LINES = 16

const ramUsedDisplay = computed(() => store.ramMetrics.used.toFixed(1))
const ramTotalDisplay = computed(() => store.ramMetrics.total.toFixed(1))
const ramPercent = computed(() => {
  const m = store.ramMetrics
  if (!m.total) return 0
  return Math.round((m.used / m.total) * 100)
})
const cpuDisplay = computed(() => {
  const cpu = store.server?.runtime?.cpu
  return typeof cpu === 'number' ? `${cpu}%` : '—'
})
const recentLogLines = computed(() => {
  const lines = store.logs.stdout || []
  return lines.slice(-RECENT_LOG_PREVIEW_LINES)
})
const modPreview = computed(() => store.installedMods.slice(0, 4))
</script>

<template>
  <div class="overview-page">
    <section class="overview-page__stats">
      <StatCard label="Players" :value="store.serverStatus.players.online" :unit="store.serverStatus.players.max ? `/${store.serverStatus.players.max}` : ''" />
      <StatCard label="Uptime" :value="store.serverStatus.uptime" />
      <StatCard label="TPS" :value="store.serverStatus.tps" :accent="store.serverStatus.status === 'running' ? 'success' : 'default'" />
      <StatCard label="Mods" :value="store.installedMods.length" :accent="store.installedMods.length > 0 ? 'primary' : 'default'" />
    </section>

    <Panel v-if="store.activeModpack" title="Active modpack">
      <div class="overview-page__modpack">
        <span class="overview-page__modpack-name">{{ store.activeModpack.name || store.activeModpack.projectId }}</span>
        <span class="overview-page__modpack-version">{{ store.activeModpack.version }}</span>
      </div>
    </Panel>

    <section class="overview-page__row">
      <div class="overview-page__col">
        <Panel title="Performance">
          <div class="overview-page__perf">
            <div class="overview-page__perf-row">
              <span class="overview-page__perf-label">RAM</span>
              <span class="overview-page__perf-value">{{ ramUsedDisplay }} / {{ ramTotalDisplay }} GB</span>
            </div>
            <div class="overview-page__bar">
              <div class="overview-page__bar-fill" :style="{ width: ramPercent + '%' }"></div>
            </div>
            <div class="overview-page__perf-meta">
              <span>{{ ramPercent }}%</span>
              <span>CPU {{ cpuDisplay }}</span>
            </div>
          </div>
        </Panel>

        <Panel title="Recent logs">
          <template #action>
            <a class="overview-page__panel-link" @click.prevent="store.goToConsole">Console →</a>
          </template>
          <div class="overview-page__logs">
            <div v-if="!recentLogLines.length" class="overview-page__empty">No logs yet.</div>
            <div v-else v-for="(line, i) in recentLogLines" :key="i" class="overview-page__log-line">
              {{ line }}
            </div>
          </div>
        </Panel>
      </div>

      <div class="overview-page__col">
        <Panel title="Installed mods">
          <template #action>
            <a class="overview-page__panel-link" @click.prevent="store.goToMods">Manage →</a>
          </template>
          <div v-if="!modPreview.length" class="overview-page__empty">No mods installed.</div>
          <ul v-else class="overview-page__mods">
            <li v-for="mod in modPreview" :key="mod.path" class="overview-page__mod">
              <span class="overview-page__mod-name">{{ mod.name }}</span>
              <span class="overview-page__mod-version">{{ mod.version }}</span>
            </li>
          </ul>
        </Panel>

        <Panel title="Quick actions">
          <div class="overview-page__qa-grid">
            <button type="button" class="overview-page__qa" :disabled="store.backupLoading" @click="store.createBackupAction">
              <span class="overview-page__qa-title">{{ store.backupLoading ? 'Creating…' : 'Backup' }}</span>
              <span class="overview-page__qa-sub">Create snapshot</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToConsole">
              <span class="overview-page__qa-title">Console</span>
              <span class="overview-page__qa-sub">View logs</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToSettings">
              <span class="overview-page__qa-title">Properties</span>
              <span class="overview-page__qa-sub">server.properties</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToSettings">
              <span class="overview-page__qa-title">World</span>
              <span class="overview-page__qa-sub">World config</span>
            </button>
          </div>
        </Panel>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.overview-page__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  min-width: 0;
}

.overview-page__modpack {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.overview-page__modpack-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.overview-page__modpack-version {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.overview-page__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
}

.overview-page__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
}

.overview-page__perf {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.overview-page__perf-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.overview-page__perf-label {
  color: var(--text-secondary);
}

.overview-page__perf-value {
  color: var(--text-secondary);
}

.overview-page__bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.overview-page__bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-pill);
  transition: width 0.3s ease;
}

.overview-page__perf-meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.overview-page__panel-link {
  font-size: var(--text-xs);
  color: var(--primary);
  cursor: pointer;
  text-decoration: none;
}

.overview-page__panel-link:hover {
  text-decoration: underline;
}

.overview-page__logs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  width: 100%;
  min-height: 14rem;
  max-height: 22rem;
  overflow-x: hidden;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.overview-page__log-line {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.overview-page__empty {
  color: var(--text-disabled);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  padding: var(--space-2) 0;
}

.overview-page__mods {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.overview-page__mod {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}

.overview-page__mod:last-child {
  border-bottom: none;
}

.overview-page__mod-name {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.overview-page__mod-version {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  flex-shrink: 0;
  margin-left: var(--space-3);
}

.overview-page__qa-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.overview-page__qa {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.overview-page__qa:hover:not(:disabled) {
  border-color: var(--text-disabled);
}

.overview-page__qa:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.overview-page__qa:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.overview-page__qa-title {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.overview-page__qa-sub {
  font-size: var(--text-xs);
  color: var(--text-disabled);
}
</style>
