<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const servers = ref([
  {
    id: 1,
    name: 'Main Survival',
    status: 'running',
    version: '1.21.3',
    loader: 'Fabric',
    players: { online: 12, max: 50 },
    mods: 23,
    uptime: '5d 12h',
    ip: 'play.example.com'
  },
  {
    id: 2,
    name: 'Creative Build',
    status: 'running',
    version: '1.21.3',
    loader: 'Fabric',
    players: { online: 3, max: 20 },
    mods: 15,
    uptime: '2d 8h',
    ip: 'creative.example.com'
  },
  {
    id: 3,
    name: 'Modded Adventure',
    status: 'stopped',
    version: '1.20.1',
    loader: 'Forge',
    players: { online: 0, max: 30 },
    mods: 156,
    uptime: null,
    ip: 'adventure.example.com'
  },
  {
    id: 4,
    name: 'Testing',
    status: 'stopped',
    version: '1.21.3',
    loader: 'Fabric',
    players: { online: 0, max: 10 },
    mods: 8,
    uptime: null,
    ip: 'test.example.com'
  }
])

const selectServer = (id) => {
  router.push(`/server/${id}`)
}
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
          <router-link to="/api-testing" class="nav-item">API Testing</router-link>
        </nav>
      </div>
    </header>

    <main class="main">
      <div class="page-header">
        <div>
          <h2 class="page-title">Server Overview</h2>
          <p class="page-subtitle">Manage your Minecraft servers</p>
        </div>
        <button class="btn-primary">+ New Server</button>
      </div>

      <div class="stats">
        <div class="stat-card">
          <div class="stat-label">Total</div>
          <div class="stat-value">{{ servers.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Running</div>
          <div class="stat-value stat-success">{{ servers.filter(s => s.status === 'running').length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Players</div>
          <div class="stat-value">{{ servers.reduce((sum, s) => sum + s.players.online, 0) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Mods</div>
          <div class="stat-value">{{ servers.reduce((sum, s) => sum + s.mods, 0) }}</div>
        </div>
      </div>

      <div class="servers">
        <div 
          v-for="server in servers" 
          :key="server.id" 
          class="server-card"
          @click="selectServer(server.id)"
        >
          <div class="server-status" :class="server.status"></div>
          <div class="server-content">
            <div class="server-top">
              <h3 class="server-name">{{ server.name }}</h3>
              <div class="server-badge" :class="server.status">
                {{ server.status === 'running' ? 'Running' : 'Stopped' }}
              </div>
            </div>
            <div class="server-info">
              <div class="info-item">
                <span class="info-label">Version</span>
                <span class="info-value">{{ server.version }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">Loader</span>
                <span class="info-value">{{ server.loader }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">Players</span>
                <span class="info-value">{{ server.players.online }}/{{ server.players.max }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">Mods</span>
                <span class="info-value">{{ server.mods }}</span>
              </div>
              <div class="info-item" v-if="server.uptime">
                <span class="info-label">Uptime</span>
                <span class="info-value">{{ server.uptime }}</span>
              </div>
            </div>
            <div class="server-ip">{{ server.ip }}</div>
          </div>
          <div class="server-actions">
            <button 
              class="action-btn"
              :class="server.status === 'running' ? 'btn-stop' : 'btn-start'"
              @click.stop
            >
              {{ server.status === 'running' ? 'Stop' : 'Start' }}
            </button>
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
  padding: 1.25rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.brand-icon {
  font-size: 1.75rem;
}

.brand-name {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #f1f5f9;
}

.nav {
  display: flex;
  gap: 0.5rem;
}

.nav-item {
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  color: #94a3b8;
  text-decoration: none;
  font-weight: 500;
  transition: all 0.2s;
}

.nav-item:hover {
  background: #334155;
  color: #e2e8f0;
}

.nav-item.active {
  background: #3b82f6;
  color: white;
}

/* Main */
.main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.page-title {
  margin: 0 0 0.5rem 0;
  font-size: 2rem;
  font-weight: 700;
  color: #f1f5f9;
}

.page-subtitle {
  margin: 0;
  color: #94a3b8;
  font-size: 1rem;
}

.btn-primary {
  padding: 0.75rem 1.5rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #2563eb;
  transform: translateY(-2px);
}

/* Stats */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 1.5rem;
}

.stat-label {
  color: #94a3b8;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #f1f5f9;
}

.stat-success {
  color: #10b981;
}

/* Servers */
.servers {
  display: grid;
  gap: 1.25rem;
}

.server-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  gap: 1.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.server-card:hover {
  border-color: #3b82f6;
  transform: translateX(4px);
}

.server-status {
  width: 4px;
  border-radius: 4px;
  flex-shrink: 0;
}

.server-status.running {
  background: #10b981;
}

.server-status.stopped {
  background: #64748b;
}

.server-content {
  flex: 1;
}

.server-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.server-name {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #f1f5f9;
}

.server-badge {
  padding: 0.375rem 0.875rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.server-badge.running {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.server-badge.stopped {
  background: rgba(100, 116, 139, 0.2);
  color: #94a3b8;
}

.server-info {
  display: flex;
  gap: 2rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.info-label {
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.info-value {
  color: #e2e8f0;
  font-weight: 600;
}

.server-ip {
  color: #64748b;
  font-family: 'Courier New', monospace;
  font-size: 0.875rem;
}

.server-actions {
  display: flex;
  align-items: center;
}

.action-btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-start {
  background: #10b981;
  color: white;
}

.btn-start:hover {
  background: #059669;
}

.btn-stop {
  background: #ef4444;
  color: white;
}

.btn-stop:hover {
  background: #dc2626;
}

@media (max-width: 1024px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    gap: 1rem;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }

  .stats {
    grid-template-columns: 1fr;
  }

  .server-card {
    flex-direction: column;
  }

  .server-status {
    width: 100%;
    height: 4px;
  }

  .server-info {
    gap: 1rem;
  }
}
</style>
