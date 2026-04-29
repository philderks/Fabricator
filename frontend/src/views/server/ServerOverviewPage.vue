<script setup>
import { computed } from 'vue'
import StatCard from '../../components/ui/StatCard.vue'
import Panel from '../../components/ui/Panel.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

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
      </div>
    </section>
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

.overview-page__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

.overview-page__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
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
</style>
