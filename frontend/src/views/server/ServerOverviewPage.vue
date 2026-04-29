<script setup>
import StatCard from '../../components/ui/StatCard.vue'
import Panel from '../../components/ui/Panel.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()
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
        <span class="overview-page__modpack-name">{{ store.activeModpack.title || store.activeModpack.projectId }}</span>
        <span class="overview-page__modpack-version">{{ store.activeModpack.version }}</span>
      </div>
    </Panel>
  </div>
</template>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.overview-page__stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
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
</style>
