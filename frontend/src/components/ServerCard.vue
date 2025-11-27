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
