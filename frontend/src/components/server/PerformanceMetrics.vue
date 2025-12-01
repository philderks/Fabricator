<script setup>
import { computed } from 'vue'

const props = defineProps({
  ram: {
    type: Object,
    required: true
  }
})

const ramPercent = computed(() => {
  if (!props.ram || !props.ram.total) {
    return 0
  }
  return Math.min(100, Math.max(0, (props.ram.used / props.ram.total) * 100))
})

const ramLabel = computed(() => {
  if (!props.ram) {
    return '0 GB'
  }
  const usedValue = typeof props.ram.used === 'number' ? props.ram.used : 0
  const totalValue = typeof props.ram.total === 'number' ? props.ram.total : 0
  const used = usedValue.toFixed(usedValue >= 10 ? 1 : 2)
  const total = totalValue.toFixed(totalValue >= 10 ? 0 : 1)
  return `${used} / ${total} GB`
})
</script>

<template>
  <div class="performance">
    <div class="perf-item">
      <div class="perf-top">
        <div>
          <span class="perf-label">RAM Usage</span>
          <div class="perf-value">{{ ramLabel }}</div>
        </div>
        <span class="perf-percent">{{ ramPercent.toFixed(0) }}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: ramPercent + '%' }"></div>
      </div>
      <p class="perf-hint" v-if="!props.ram.running">Server muss laufen, um Live-Daten zu sammeln.</p>
    </div>
  </div>
</template>

<style scoped>
.performance {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.perf-item {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.perf-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.perf-label {
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 500;
}

.perf-value {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 600;
}

.perf-percent {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 1rem;
}

.progress-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transition: width 0.3s;
}

.perf-hint {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-muted);
}
</style>
