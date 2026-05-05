<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import StatusPill from '../ui/StatusPill.vue'
import AppButton from '../ui/AppButton.vue'

const props = defineProps({
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
  }
})

defineEmits(['start', 'stop', 'restart'])

const route = useRoute()

const ROUTE_TITLE = {
  ServerOverview: 'Overview',
  ServerConsole:  'Console',
  ServerMods:     'Mods',
  ServerFiles:    'Files',
  ServerSettings: 'Settings'
}

const pageTitle = computed(() => ROUTE_TITLE[route.name] || '')

const pillStatus = computed(() => {
  const allowed = ['running', 'stopped', 'pending', 'installing', 'failed', 'unknown']
  return allowed.includes(props.serverStatus.status) ? props.serverStatus.status : 'unknown'
})

const pillSub = computed(() => {
  const loader = props.serverStatus.loader
  const version = props.serverStatus.version
  if (loader && version && version !== '—') {
    return `${loader} ${version}`
  }
  return loader || ''
})

const isRunning = computed(() => props.serverStatus.status === 'running')
</script>

<template>
  <header class="app-topbar">
    <div class="app-topbar__title">{{ pageTitle }}</div>
    <div class="app-topbar__right">
      <StatusPill :status="pillStatus" :label="statusLabel" :sub="pillSub" />

      <AppButton
        variant="ghost"
        size="md"
        :disabled="actionState.restart || !isRunning"
        :loading="actionState.restart"
        @click="$emit('restart')"
      >
        {{ actionState.restart ? 'Restarting' : 'Restart' }}
      </AppButton>

      <AppButton
        v-if="isRunning"
        variant="danger"
        size="md"
        :disabled="actionState.stop"
        :loading="actionState.stop"
        @click="$emit('stop')"
      >
        {{ actionState.stop ? 'Stopping' : 'Stop' }}
      </AppButton>
      <AppButton
        v-else
        variant="primary"
        size="md"
        :disabled="actionState.start || startLocked"
        :loading="actionState.start"
        @click="$emit('start')"
      >
        {{ startButtonLabel }}
      </AppButton>
    </div>
  </header>
</template>

<style scoped>
.app-topbar {
  height: var(--app-chrome-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.app-topbar__title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.app-topbar__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
