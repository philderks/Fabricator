<script setup>
defineProps({
  server: {
    type: Object,
    required: true
  }
})

defineEmits(['click'])
</script>

<template>
  <div class="server-card" @click="$emit('click', server.id)">
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
</template>

<style scoped>
.server-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  gap: 1.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.server-card:hover {
  border-color: var(--border-hover);
  transform: translateX(4px);
}

.server-status {
  width: 4px;
  border-radius: 4px;
  flex-shrink: 0;
}

.server-status.running {
  background: var(--success);
}

.server-status.stopped {
  background: var(--text-disabled);
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
  color: var(--text-primary);
}

.server-badge {
  padding: 0.375rem 0.875rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.server-badge.running {
  background: color-mix(in oklch, var(--success) 20%, transparent);
  color: var(--success);
}

.server-badge.stopped {
  background: color-mix(in oklch, var(--text-muted) 20%, transparent);
  color: var(--text-muted);
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
  color: var(--text-disabled);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.info-value {
  color: var(--text-secondary);
  font-weight: 600;
}

.server-ip {
  color: var(--text-disabled);
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
  background: var(--success);
  color: white;
}

.btn-start:hover {
  background: var(--success-dark);
}

.btn-stop {
  background: var(--danger);
  color: white;
}

.btn-stop:hover {
  background: var(--danger-dark);
}

@media (max-width: 768px) {
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
