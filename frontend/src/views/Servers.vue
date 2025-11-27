<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import ServerCard from '../components/ServerCard.vue'
import StatCard from '../components/StatCard.vue'

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
        <StatCard label="Total" :value="servers.length" />
        <StatCard label="Running" :value="servers.filter(s => s.status === 'running').length" highlight />
        <StatCard label="Players" :value="servers.reduce((sum, s) => sum + s.players.online, 0)" />
        <StatCard label="Mods" :value="servers.reduce((sum, s) => sum + s.mods, 0)" />
      </div>

      <div class="servers">
        <ServerCard 
          v-for="server in servers" 
          :key="server.id" 
          :server="server"
          @click="selectServer"
        />
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

.servers {
  display: grid;
  gap: 1.25rem;
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

}
</style>
