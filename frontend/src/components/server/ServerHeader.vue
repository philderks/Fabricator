<script setup>
const props = defineProps({
  server: {
    type: Object,
    default: null
  },
  serverLoading: {
    type: Boolean,
    default: false
  },
  serverStatus: {
    type: Object,
    required: true
  },
  statusLabel: {
    type: String,
    required: true
  },
  actionState: {
    type: Object,
    required: true
  },
  startLocked: {
    type: Boolean,
    default: false
  },
  startButtonLabel: {
    type: String,
    required: true
  },
  deletingServer: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['start', 'stop', 'restart', 'delete'])

const handleStart = () => {
  if (props.startLocked || props.actionState.start) {
    return
  }
  emit('start')
}

const handleStop = () => {
  if (props.actionState.stop) {
    return
  }
  emit('stop')
}

const handleRestart = () => {
  if (props.actionState.restart || props.serverStatus.status !== 'running') {
    return
  }
  emit('restart')
}

const handleDelete = () => {
  emit('delete')
}
</script>

<template>
  <header class="header">
    <div class="header-content" v-if="!serverLoading && server">
      <div class="brand">
        <router-link to="/" class="back-btn">←</router-link>
        <div>
          <h1 class="server-title">{{ serverStatus.name }}</h1>
          <div class="server-meta">
            <span class="status-indicator" :class="serverStatus.status"></span>
            <span class="status-text">{{ statusLabel }}</span>
            <span class="separator">•</span>
            <span>{{ serverStatus.loader }} {{ serverStatus.version }}</span>
          </div>
        </div>
      </div>
      <div class="server-controls">
        <button class="btn btn-outline" :disabled="deletingServer" @click="handleDelete">
          {{ deletingServer ? 'Deleting…' : 'Delete' }}
        </button>
        <button
          class="btn btn-danger"
          v-if="serverStatus.status === 'running'"
          :disabled="actionState.stop"
          @click="handleStop"
        >
          {{ actionState.stop ? 'Stopping…' : 'Stop' }}
        </button>
        <button
          class="btn btn-success"
          v-else
          :disabled="actionState.start || startLocked"
          @click="handleStart"
        >
          {{ startButtonLabel }}
        </button>
        <button
          class="btn btn-secondary"
          :disabled="actionState.restart || serverStatus.status !== 'running'"
          @click="handleRestart"
        >
          {{ actionState.restart ? 'Restarting…' : 'Restart' }}
        </button>
      </div>
    </div>
    <div class="header-content" v-else>
      <div class="brand">
        <router-link to="/" class="back-btn">←</router-link>
        <div>
          <div class="skeleton skeleton-title"></div>
          <div class="skeleton skeleton-subtitle"></div>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 1.25rem;
  transition: all 0.2s;
}

.back-btn:hover {
  background: var(--primary);
  color: white;
}

.server-title {
  margin: 0 0 0.375rem 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.server-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.running {
  background: var(--success);
}

.status-indicator.stopped {
  background: var(--text-disabled);
}

.status-indicator.pending,
.status-indicator.installing {
  background: #fbbf24;
}

.status-indicator.failed {
  background: #ef4444;
}

.status-text {
  font-weight: 500;
}

.separator {
  color: var(--text-disabled);
}

.server-controls {
  display: flex;
  gap: 0.75rem;
}

.skeleton {
  background: linear-gradient(90deg, var(--bg-tertiary), var(--bg-secondary), var(--bg-tertiary));
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}

.skeleton-title {
  width: 180px;
  height: 24px;
  margin-bottom: 0.5rem;
}

.skeleton-subtitle {
  width: 140px;
  height: 16px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
