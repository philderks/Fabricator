<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import ServerCard from '../components/ui/ServerCard.vue'
import StatCard from '../components/ui/StatCard.vue'
import ServerCreateModal from '../components/modals/ServerCreateModal.vue'
import { getServers, startServer, stopServer, getSystemMetrics } from '../api/servers'
import { useToast } from '../composables/useToast'

const router = useRouter()
const toast = useToast()

const servers = ref([])
const loading = ref(true)
const showCreateModal = ref(false)
const serverActions = ref({})
const systemMetrics = ref({ cpuPercent: null })
let systemMetricsIntervalId = null

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

const handleCreateServer = async (createdServer) => {
  try {
    toast.success(`Server "${createdServer.name}" created successfully!`, 'Server Created')
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

const handleStartStop = async (id, actionFn, successMessage, errorTitle) => {
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
    toast.error('Request failed', errorTitle)
  } finally {
    setServerActionState(id, false)
    await loadServers()
  }
}

const handleStart = (id) => handleStartStop(id, startServer, 'Server start requested', 'Start Failed')
const handleStop = (id) => handleStartStop(id, stopServer, 'Server stop requested', 'Stop Failed')

const cpuStatLabel = computed(() => {
  const value = systemMetrics.value.cpuPercent
  if (typeof value !== 'number') {
    return '—'
  }
  return `${value}%`
})

// Load servers on mount and refresh system metrics periodically
onMounted(() => {
  loadServers()
  loadSystemMetrics()
  systemMetricsIntervalId = setInterval(loadSystemMetrics, 2500)
})

onUnmounted(() => {
  if (systemMetricsIntervalId) {
    clearInterval(systemMetricsIntervalId)
    systemMetricsIntervalId = null
  }
})
</script>

<template>
  <div class="page">
    <header class="header">
      <div class="header-content">
        <div class="brand">
          <div class="brand-icon">⚙️</div>
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

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
}

.loading-state p {
  color: var(--text-muted);
  font-size: 1rem;
}

.empty-state svg {
  color: var(--text-muted);
  margin-bottom: 1.5rem;
}

.empty-state h3 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.empty-state p {
  font-size: 1rem;
  color: var(--text-muted);
  margin: 0 0 2rem 0;
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
}
</style>
