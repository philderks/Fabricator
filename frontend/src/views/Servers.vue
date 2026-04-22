<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import ServerCard from '../components/ui/ServerCard.vue'
import StatCard from '../components/ui/StatCard.vue'
import ServerCreateModal from '../components/modals/ServerCreateModal.vue'
import JavaInstallModal from '../components/modals/JavaInstallModal.vue'
import {
  getServers,
  startServer,
  stopServer,
  getSystemMetrics,
  getUpdateStatus,
  triggerUpdate
} from '../api/servers'
import { useToast } from '../composables/useToast'

const router = useRouter()
const toast = useToast()

const servers = ref([])
const loading = ref(true)
const showCreateModal = ref(false)
const showJavaModal = ref(false)
const pendingJavaServer = ref(null)
const serverActions = ref({})
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

const setServerActionState = (id, value) => {
  const next = { ...serverActions.value }
  if (value) {
    next[id] = true
  } else {
    delete next[id]
  }
  serverActions.value = next
}

const handleStartStop = async (id, actionFn, successMessage, errorTitle, { isStart = false } = {}) => {
  if (serverActions.value[id]) {
    return
  }
  setServerActionState(id, true)
  try {
    const result = await actionFn(id)
    if (result.success) {
      toast.success(successMessage, 'Success')
    } else {
      toast.error(result.message || 'Operation failed', errorTitle)
    }
  } catch (error) {
    console.error(error)
    if (isStart && (error.data?.java_missing || error.data?.java_too_old)) {
      pendingJavaServer.value = servers.value.find(s => s.id === id) || { id }
      showJavaModal.value = true
    } else {
      toast.error(error.message || 'Request failed', errorTitle)
    }
  } finally {
    setServerActionState(id, false)
    await loadServers()
  }
}

const handleStart = (id) => handleStartStop(id, startServer, 'Server start requested', 'Start Failed', { isStart: true })
const handleStop = (id) => handleStartStop(id, stopServer, 'Server stop requested', 'Stop Failed')

const handleJavaInstalled = () => {
  const pending = pendingJavaServer.value
  showJavaModal.value = false
  pendingJavaServer.value = null
  if (pending?.id) {
    handleStart(pending.id)
  }
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
  <div class="page">
    <header class="header">
      <div class="header-content">
        <div class="brand">
          <img src="/favicon.svg" alt="Fabricator" class="brand-logo" />
          <h1 class="brand-name">Fabricator</h1>
        </div>
        <nav class="nav">
          <router-link to="/" class="nav-item active">Servers</router-link>
        </nav>
      </div>
    </header>

    <main class="main">
      <div class="content">
        <div class="page-header">
          <div>
            <h2 class="page-title">Server Overview</h2>
            <p class="page-subtitle">Manage your Minecraft servers</p>
          </div>
          <button class="btn btn-primary" @click="showCreateModal = true">+ New Server</button>
        </div>

        <div class="stats">
          <StatCard label="Total" :value="servers.length" />
          <StatCard label="Running" :value="servers.filter(s => s.status === 'running').length" highlight />
          <StatCard label="Players" :value="servers.reduce((sum, s) => sum + s.players.online, 0)" />
          <StatCard label="CPU" :value="cpuStatLabel" />
        </div>

        <section class="update-card">
          <div class="update-card__meta">
            <h3>Fabricator Update</h3>
            <p class="update-card__subtitle">
              Current: {{ updateState.currentVersion || 'unknown' }} · Latest:
              {{ updateState.latestVersion || 'unknown' }}
            </p>
            <p class="update-card__status">{{ updateStatusLabel }}</p>
            <p v-if="updateState.lastError" class="update-card__error">
              {{ updateState.lastError }}
            </p>
          </div>
          <div class="update-card__actions">
            <button class="btn" :disabled="updateStatusLoading" @click="loadUpdateState()">
              {{ updateStatusLoading ? 'Checking…' : 'Check for Updates' }}
            </button>
            <button class="btn btn-primary" :disabled="!canTriggerUpdate" @click="runUpdate">
              {{ updateState.inProgress || updateTriggering ? 'Updating…' : 'Update Fabricator' }}
            </button>
          </div>
        </section>

        <div v-if="loading" class="loading-state">
          <p>Loading servers...</p>
        </div>

        <div v-else-if="servers.length === 0" class="empty-state">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
            <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
            <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <h3>No servers yet</h3>
          <p>Create your first Minecraft server to get started</p>
          <button class="btn btn-primary" @click="showCreateModal = true">+ Create Server</button>
        </div>

        <div v-else class="servers">
          <ServerCard 
            v-for="server in servers" 
            :key="server.id" 
            :server="server"
            :busy="!!serverActions[server.id]"
            @click="selectServer"
            @start="handleStart"
            @stop="handleStop"
          />
        </div>
      </div>
    </main>

    <ServerCreateModal
      :show="showCreateModal"
      @close="showCreateModal = false"
      @create="handleCreateServer"
    />

    <JavaInstallModal
      :show="showJavaModal"
      :mc-version="pendingJavaServer?.version || ''"
      @close="showJavaModal = false"
      @java-installed="handleJavaInstalled"
    />
  </div>
</template>

<style scoped>
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.servers {
  display: grid;
  gap: 1.25rem;
}

.update-card {
  margin-bottom: 1.5rem;
  border: 1px solid var(--border-subtle, #dcdfe6);
  border-radius: 12px;
  padding: 1rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  background: var(--panel-bg, #fff);
}

.update-card__meta h3 {
  margin: 0;
  font-size: 1rem;
}

.update-card__subtitle {
  margin: 0.35rem 0 0;
  opacity: 0.8;
}

.update-card__status {
  margin: 0.35rem 0 0;
  font-weight: 600;
}

.update-card__error {
  margin: 0.35rem 0 0;
  color: #d72c2c;
}

.update-card__actions {
  display: flex;
  gap: 0.6rem;
}

@media (max-width: 1024px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats {
    grid-template-columns: 1fr;
  }

  .update-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .update-card__actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
