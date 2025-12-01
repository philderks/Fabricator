<script setup>
import { computed } from 'vue'

const props = defineProps({
  serverStatus: {
    type: Object,
    required: true
  },
  statusLabel: {
    type: String,
    required: true
  },
  logs: {
    type: Object,
    required: true
  },
  logsLoading: {
    type: Boolean,
    default: false
  },
  consoleCommand: {
    type: String,
    default: ''
  },
  canSendCommand: {
    type: Boolean,
    default: false
  },
  commandSending: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['refresh-logs', 'update:consoleCommand', 'send-command'])

const consoleCommandModel = computed({
  get: () => props.consoleCommand,
  set: (value) => emit('update:consoleCommand', value)
})

const handleRefresh = () => emit('refresh-logs')
const handleSendCommand = () => emit('send-command')
</script>

<template>
  <div class="console-tab">
    <div class="console-toolbar">
      <div class="status-pill" :class="serverStatus.status">
        Server {{ statusLabel }}
      </div>
      <button class="btn btn-secondary" :disabled="logsLoading" @click="handleRefresh">
        {{ logsLoading ? 'Refreshing…' : 'Refresh Logs' }}
      </button>
    </div>
    <div class="console-command">
      <input
        v-model="consoleCommandModel"
        class="command-input"
        type="text"
        placeholder="Enter server command (e.g., say Hello)"
        :disabled="!canSendCommand || commandSending"
        @keyup.enter="handleSendCommand"
      >
      <button
        class="btn btn-primary"
        :disabled="!canSendCommand || commandSending || !consoleCommandModel.trim()"
        @click="handleSendCommand"
      >
        {{ commandSending ? 'Sending…' : 'Send Command' }}
      </button>
    </div>
    <p class="command-hint" v-if="!canSendCommand">
      Server must be running to accept console commands.
    </p>
    <div class="console-output">
      <div class="console-stream">
        <div class="console-stream__header">STDOUT</div>
        <div class="console-stream__body">
          <template v-if="logs.stdout?.length">
            <pre v-for="(line, idx) in logs.stdout" :key="`stdout-${idx}`">{{ line }}</pre>
          </template>
          <p v-else class="console-empty">No output yet.</p>
        </div>
      </div>
      <div class="console-stream">
        <div class="console-stream__header">STDERR</div>
        <div class="console-stream__body">
          <template v-if="logs.stderr?.length">
            <pre v-for="(line, idx) in logs.stderr" :key="`stderr-${idx}`">{{ line }}</pre>
          </template>
          <p v-else class="console-empty">No errors reported.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.console-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.console-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.console-command {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.command-input {
  flex: 1;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
}

.command-input:focus {
  outline: none;
  border-color: var(--primary);
}

.command-hint {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.status-pill {
  padding: 0.375rem 0.75rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: white;
}

.status-pill.running {
  background: var(--success);
}

.status-pill.stopped {
  background: var(--text-disabled);
}

.status-pill.pending,
.status-pill.installing {
  background: #fbbf24;
}

.status-pill.failed {
  background: #ef4444;
}

.console-output {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.console-stream__header {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.console-stream__body {
  background: black;
  color: #e5e7eb;
  padding: 1rem;
  border-radius: 8px;
  min-height: 240px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.console-stream__body pre {
  margin: 0;
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
  font-size: 0.875rem;
  line-height: 1.4;
  white-space: pre-wrap;
}

.console-empty {
  margin: 0;
  color: #94a3b8;
}
</style>
