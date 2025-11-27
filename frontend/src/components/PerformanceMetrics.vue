<script setup>
defineProps({
  cpu: {
    type: Number,
    required: true
  },
  ram: {
    type: Object,
    required: true
  }
})
</script>

<template>
  <div class="performance">
    <div class="perf-item">
      <div class="perf-top">
        <span class="perf-label">CPU Usage</span>
        <span class="perf-value">{{ cpu }}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: cpu + '%' }"></div>
      </div>
    </div>
    <div class="perf-item">
      <div class="perf-top">
        <span class="perf-label">RAM Usage</span>
        <span class="perf-value">{{ ram.used }}GB / {{ ram.total }}GB</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: (ram.used / ram.total * 100) + '%' }"></div>
      </div>
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
  gap: 0.625rem;
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
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 600;
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
</style>
