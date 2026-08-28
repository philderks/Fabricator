<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import StatusPill from '../ui/StatusPill.vue'
import AppButton from '../ui/AppButton.vue'
import MobileMenuButton from './MobileMenuButton.vue'
import { contentLabel } from '../../utils/loaderKind'

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

defineEmits(['start', 'stop', 'restart', 'install'])

const route = useRoute()

const ROUTE_TITLE = {
  ServerOverview: 'Overview',
  ServerConsole:  'Console',
  ServerPlayers:  'Players',
  ServerMods:     'Mods',
  ServerFiles:    'Files',
  ServerBackups:  'Backups',
  ServerPlayit:   'playit.gg',
  ServerSettings: 'Properties',
  ServerGeneralSettings: 'Settings'
}

const pageTitle = computed(() => {
  // The add-on page is "Plugins" for Bukkit-family servers, "Mods" otherwise.
  if (route.name === 'ServerMods') {
    return contentLabel(props.serverStatus.loader)
  }
  return ROUTE_TITLE[route.name] || ''
})

// StatusPill.vue owns the allowlist via its prop validator and falls back
// to STATUS_META.unknown for unknown values — gating it here would just
// duplicate that logic (F6/CC5).
const pillStatus = computed(() => props.serverStatus.status || 'unknown')

const pillSub = computed(() => {
  const loader = props.serverStatus.loader
  const version = props.serverStatus.version
  if (loader && version && version !== '—') {
    return `${loader} ${version}`
  }
  return loader || ''
})

const isRunning = computed(() => props.serverStatus.status === 'running')

// A 'pending' server (created but never installed) turns the start button
// into an actionable Install control instead of a dead locked one.
const isPending = computed(() => props.serverStatus.status === 'pending')
</script>

<template>
  <header class="app-topbar">
    <div class="app-topbar__lead">
      <MobileMenuButton />
      <div class="app-topbar__title">{{ pageTitle }}</div>
    </div>
    <div class="app-topbar__right">
      <StatusPill :status="pillStatus" :label="statusLabel" :sub="pillSub" />

      <div class="app-topbar__actions">
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
          :disabled="isPending ? actionState.install : (actionState.start || startLocked)"
          :loading="isPending ? actionState.install : actionState.start"
          @click="$emit(isPending ? 'install' : 'start')"
        >
          {{ startButtonLabel }}
        </AppButton>
      </div>
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

.app-topbar__lead {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.app-topbar__title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-topbar__right,
.app-topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* Mobile: the status pill plus two buttons can't share a row with the title at
   phone widths, so the bar becomes two rows — title (with the menu button) on
   top, controls below. Height goes auto to let the second row exist; the header
   token stays as the floor so a bar with no controls still lines up. */
@media (max-width: 768px) {
  .app-topbar {
    height: auto;
    min-height: var(--app-chrome-header-height);
    flex-wrap: wrap;
    row-gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
  }

  .app-topbar__lead {
    flex: 1 1 auto;
  }

  .app-topbar__title {
    font-size: var(--text-md);
  }

  /* Full-width basis forces the wrap onto row two regardless of how wide the
     pill's loader/version text happens to render. */
  .app-topbar__right {
    flex: 1 0 100%;
    justify-content: space-between;
    min-width: 0;
  }
}
</style>
