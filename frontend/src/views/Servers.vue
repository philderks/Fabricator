<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '../components/ui/StatCard.vue'
import StatusPill from '../components/ui/StatusPill.vue'
import Panel from '../components/ui/Panel.vue'
import AppButton from '../components/ui/AppButton.vue'
import ServerCreateModal from '../components/modals/ServerCreateModal.vue'
import {
  getServers,
  getSystemMetrics,
  getUpdateStatus,
  triggerUpdate
} from '../api/servers'
import { useToast } from '../composables/useToast'

const router = useRouter()
const toast = useToast()

const servers = ref([])
const loading = ref(true)
const errorMessage = ref(null)
// Provided by RootLayout — RootTopbar's "+ Add server" flips it open;
// the modal close-handler writes false back through the same ref.
const showCreateModal = inject('showCreateModal', ref(false))
const systemMetrics = ref({ cpuPercent: null })
const updateState = ref({
  inProgress: false,
  currentVersion: 'unknown',
  latestVersion: null,
  updateAvailable: false,
  lastError: null,
  lastExitCode: null
})
const updateStatusLoading = ref(false)
const updateTriggering = ref(false)
let systemMetricsIntervalId = null
let updateStatusIntervalId = null

// Load servers from API
const loadServers = async () => {
  loading.value = true
  errorMessage.value = null
  try {
    const data = await getServers()
    // Transform API data to match component expectations
    servers.value = data.map(server => {
      const runtime = server.runtime || {}
      const status = runtime.status || server.status
      const loaderName = server.loader ? server.loader.charAt(0).toUpperCase() + server.loader.slice(1) : 'Unknown'
      const playersOnline = runtime.players?.online ?? 0
      const playersMax = runtime.players?.max ?? server.maxPlayers ?? 20
      return {
        id: server.id,
        name: server.name,
        status,
        version: server.version,
        loader: loaderName,
        players: { online: playersOnline, max: playersMax },
        mods: runtime.mods ?? 0,
        uptime: runtime.uptime || (status === 'running' ? '—' : null),
        ip: `localhost:${server.port}`
      }
    })
  } catch (error) {
    console.error('Failed to load servers:', error)
    errorMessage.value = error?.message || 'Failed to load servers'
    toast.error('Failed to load servers', 'Error')
  } finally {
    loading.value = false
  }
}

const loadSystemMetrics = async () => {
  try {
    const metrics = await getSystemMetrics()
    systemMetrics.value = {
      cpuPercent: metrics?.cpu?.percent ?? null
    }
  } catch (error) {
    console.error('Failed to load system metrics:', error)
    systemMetrics.value = { cpuPercent: null }
  }
}

const loadUpdateState = async ({ silent = false } = {}) => {
  if (!silent) {
    updateStatusLoading.value = true
  }
  try {
    updateState.value = await getUpdateStatus()
  } catch (error) {
    console.error('Failed to load update status:', error)
    if (!silent) {
      toast.error(error.message || 'Failed to load update status', 'Update Status')
    }
  } finally {
    if (!silent) {
      updateStatusLoading.value = false
    }
  }
}

const handleCreateServer = async (createdServer) => {
  try {
    const modpackTitle = createdServer?.modpackSelection?.title
    const modpackInstallError = createdServer?.modpackInstallError
    if (modpackInstallError) {
      toast.warning(
        `Server "${createdServer.name}" was created, but modpack install failed: ${modpackInstallError}`,
        'Modpack Install Failed'
      )
    } else {
      const message = modpackTitle
        ? `Server "${createdServer.name}" created. Selected modpack: ${modpackTitle}.`
        : `Server "${createdServer.name}" created successfully!`
      toast.success(message, 'Server Created')
    }
    await loadServers()
  } catch (error) {
    console.error('Failed to refresh servers:', error)
    toast.error('Server list could not be refreshed', 'Error')
  }
}

const selectServer = (id) => {
  router.push(`/server/${id}`)
}

const cpuStatLabel = computed(() => {
  const value = systemMetrics.value.cpuPercent
  if (typeof value !== 'number') {
    return '—'
  }
  return `${value}%`
})

const updateStatusLabel = computed(() => {
  if (updateState.value.inProgress) {
    return 'Updating…'
  }
  if (updateState.value.lastError) {
    return 'Last update failed'
  }
  if (updateState.value.lastExitCode === 0) {
    return 'Last update succeeded'
  }
  if (updateState.value.updateAvailable) {
    return 'Update available'
  }
  return 'Up to date'
})

const canTriggerUpdate = computed(() => !updateState.value.inProgress && !updateTriggering.value)

const runUpdate = async () => {
  const confirmed = window.confirm(
    'Run Fabricator update now? The service may restart briefly while preserving server data and config.'
  )
  if (!confirmed) {
    return
  }

  updateTriggering.value = true
  try {
    const result = await triggerUpdate()
    if (result.started) {
      toast.success('Update started in background', 'Fabricator Update')
      await loadUpdateState({ silent: true })
    } else {
      toast.error(result.error || 'Unable to start update', 'Fabricator Update')
    }
  } catch (error) {
    console.error('Failed to trigger update:', error)
    toast.error(error.message || 'Failed to trigger update', 'Fabricator Update')
  } finally {
    updateTriggering.value = false
  }
}

// StatusPill expects one of: running, stopped, pending, installing, failed.
// Servers.vue currently maps API status to either 'running' or 'stopped'
// (via `runtime.status || server.status`); pass the raw value through and
// fall back to 'stopped' for any unrecognised value.
const pillStatus = (status) => {
  const allowed = ['running', 'stopped', 'pending', 'installing', 'failed']
  return allowed.includes(status) ? status : 'stopped'
}


// Drives the colour of the update banner status label (action slot).
const updateStateClass = computed(() => {
  if (updateState.value.inProgress || updateTriggering.value) return 'is-updating'
  if (updateState.value.lastError) return 'is-error'
  if (updateState.value.lastExitCode === 0) return 'is-success'
  if (updateState.value.updateAvailable) return 'is-available'
  return 'is-idle'
})

// Load servers on mount and refresh system metrics periodically
onMounted(async () => {
  loadServers()
  loadSystemMetrics()
  await loadUpdateState()
  systemMetricsIntervalId = setInterval(loadSystemMetrics, 2500)
  updateStatusIntervalId = setInterval(() => {
    loadUpdateState({ silent: true })
  }, 4000)
})

onUnmounted(() => {
  if (systemMetricsIntervalId) {
    clearInterval(systemMetricsIntervalId)
    systemMetricsIntervalId = null
  }
  if (updateStatusIntervalId) {
    clearInterval(updateStatusIntervalId)
    updateStatusIntervalId = null
  }
})
</script>

<template>
  <div class="servers-page">
    <div class="servers-page__header">
      <h2 class="servers-page__title">Server Overview</h2>
      <p class="servers-page__subtitle">Manage your Minecraft servers</p>
    </div>

    <div class="servers-page__stats">
      <StatCard label="Total" :value="servers.length" />
      <StatCard
        label="Running"
        :value="servers.filter(s => s.status === 'running').length"
        accent="success"
      />
      <StatCard
        label="Players"
        :value="servers.reduce((sum, s) => sum + s.players.online, 0)"
      />
      <StatCard label="CPU" :value="cpuStatLabel" />
    </div>

    <Panel class="servers-page__update">
      <template #action>
        <span class="servers-page__update-status" :class="updateStateClass">
          {{ updateStatusLabel }}
        </span>
      </template>
      <div class="servers-page__update-body">
        <div class="servers-page__update-meta">
          <p class="servers-page__update-versions">
            <span class="servers-page__update-label">Current</span>
            <span class="servers-page__update-value">{{ updateState.currentVersion || 'unknown' }}</span>
            <span class="servers-page__update-sep">·</span>
            <span class="servers-page__update-label">Latest</span>
            <span class="servers-page__update-value">{{ updateState.latestVersion || 'unknown' }}</span>
          </p>
          <p v-if="updateState.lastError" class="servers-page__update-error">
            {{ updateState.lastError }}
          </p>
        </div>
        <div class="servers-page__update-actions">
          <AppButton
            variant="ghost"
            size="sm"
            :disabled="updateStatusLoading"
            :loading="updateStatusLoading"
            @click="loadUpdateState()"
          >
            {{ updateStatusLoading ? 'Checking' : 'Check' }}
          </AppButton>
          <AppButton
            variant="primary"
            size="sm"
            :disabled="!canTriggerUpdate"
            :loading="updateState.inProgress || updateTriggering"
            @click="runUpdate"
          >
            {{ updateState.inProgress || updateTriggering ? 'Updating' : 'Update' }}
          </AppButton>
        </div>
      </div>
    </Panel>

    <!-- State 1: Loading (first fetch in flight) -->
    <div v-if="loading" class="servers-page__state">
      <div class="servers-page__spinner" aria-hidden="true"></div>
      <p>Loading servers…</p>
    </div>

    <!-- State 2: Error (fetch failed, no data) -->
    <div v-else-if="errorMessage" class="servers-page__state servers-page__state--error">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
        <path d="M12 8V13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        <circle cx="12" cy="16" r="0.9" fill="currentColor"/>
      </svg>
      <h3>Couldn't load servers</h3>
      <p>{{ errorMessage }}</p>
      <AppButton variant="ghost" size="md" @click="loadServers">Retry</AppButton>
    </div>

    <!-- State 3: Empty (fetch succeeded, no servers) -->
    <div v-else-if="servers.length === 0" class="servers-page__state">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="2.5" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 9H15M9 13H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <h3>No servers yet</h3>
      <p>Create your first Minecraft server to get started.</p>
      <AppButton variant="primary" size="md" @click="showCreateModal = true">
        + Create your first server
      </AppButton>
    </div>

    <!-- State 4: Populated -->
    <ul v-else class="servers-page__list">
      <li v-for="server in servers" :key="server.id">
        <button
          type="button"
          class="server-card"
          @click="selectServer(server.id)"
        >
          <span class="server-card__indicator" :data-status="server.status" aria-hidden="true"></span>
          <div class="server-card__main">
            <div class="server-card__head">
              <h3 class="server-card__name">{{ server.name }}</h3>
              <StatusPill :status="pillStatus(server.status)" />
            </div>
            <dl class="server-card__meta">
              <div class="server-card__cell">
                <dt>Version</dt>
                <dd>{{ server.version }}</dd>
              </div>
              <div class="server-card__cell">
                <dt>Loader</dt>
                <dd>{{ server.loader }}</dd>
              </div>
              <div class="server-card__cell">
                <dt>Players</dt>
                <dd>{{ server.players.online }}/{{ server.players.max }}</dd>
              </div>
              <div class="server-card__cell">
                <dt>Mods</dt>
                <dd>{{ server.mods }}</dd>
              </div>
              <div class="server-card__cell" v-if="server.uptime">
                <dt>Uptime</dt>
                <dd>{{ server.uptime }}</dd>
              </div>
            </dl>
            <p class="server-card__address">{{ server.ip }}</p>
          </div>
          <span class="server-card__chevron" aria-hidden="true">→</span>
        </button>
      </li>
    </ul>

    <ServerCreateModal
      :show="showCreateModal"
      @close="showCreateModal = false"
      @create="handleCreateServer"
    />
  </div>
</template>

<style scoped>
.servers-page {
  flex: 1;
  padding: var(--space-5) var(--space-6);
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.servers-page__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.servers-page__title {
  margin: 0 0 var(--space-1) 0;
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.servers-page__subtitle {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.servers-page__stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

/* Update banner */
.servers-page__update-body {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
}

.servers-page__update-meta {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.servers-page__update-versions {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.servers-page__update-label {
  color: var(--text-muted);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.servers-page__update-value {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.servers-page__update-sep {
  color: var(--text-disabled);
}

.servers-page__update-error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--danger);
}

.servers-page__update-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.servers-page__update-status {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.servers-page__update-status.is-idle      { color: var(--text-muted); }
.servers-page__update-status.is-available { color: var(--primary); }
.servers-page__update-status.is-updating  { color: var(--warning); }
.servers-page__update-status.is-success   { color: var(--success); }
.servers-page__update-status.is-error     { color: var(--danger); }

/* States: loading / error / empty */
.servers-page__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-10) var(--space-5);
  text-align: center;
  color: var(--text-muted);
}

.servers-page__state h3 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.servers-page__state p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  max-width: 360px;
}

.servers-page__state svg {
  color: var(--text-disabled);
}

.servers-page__state--error svg {
  color: var(--danger);
}

.servers-page__spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: servers-page-spin 0.8s linear infinite;
}

@keyframes servers-page-spin {
  to { transform: rotate(360deg); }
}

/* Server list */
.servers-page__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.server-card {
  width: 100%;
  display: flex;
  align-items: stretch;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  text-align: left;
  font-family: inherit;
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.server-card:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-sm);
}

.server-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.server-card__indicator {
  width: 3px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  background: var(--text-disabled);
}

.server-card__indicator[data-status="running"]    { background: var(--success); }
.server-card__indicator[data-status="installing"] { background: var(--primary); }
.server-card__indicator[data-status="pending"]    { background: var(--warning); }
.server-card__indicator[data-status="failed"]     { background: var(--danger); }

.server-card__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.server-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
}

.server-card__name {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-card__meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
}

.server-card__cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.server-card__cell dt {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.server-card__cell dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.server-card__address {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.server-card__chevron {
  align-self: center;
  color: var(--text-disabled);
  font-size: var(--text-md);
  transition: color 0.15s ease, transform 0.15s ease;
  flex-shrink: 0;
}

.server-card:hover .server-card__chevron {
  color: var(--primary);
  transform: translateX(2px);
}

@media (max-width: 1024px) {
  .servers-page__stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .servers-page {
    padding: var(--space-4);
  }

  .servers-page__header {
    gap: var(--space-2);
  }

  .servers-page__stats {
    grid-template-columns: 1fr;
  }

  .servers-page__update-body {
    flex-direction: column;
    align-items: flex-start;
  }

  .servers-page__update-actions {
    width: 100%;
  }

  .server-card {
    flex-direction: column;
    align-items: stretch;
  }

  .server-card__indicator {
    width: 100%;
    height: 3px;
  }

  .server-card__chevron {
    display: none;
  }
}
</style>
