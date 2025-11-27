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
      <div class="content">
        <div class="page-header">
          <div>
            <h2 class="page-title">Server Overview</h2>
            <p class="page-subtitle">Manage your Minecraft servers</p>
          </div>
          <button class="btn btn-primary">+ New Server</button>
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
      </div>
    </main>
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
