<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServerStore } from '../../stores/server'

const route = useRoute()
const router = useRouter()
const store = useServerStore()

const open = ref(false)

const currentId = computed(() => route.params.id)

const currentServer = computed(() => {
  const found = store.serversList.find((s) => s.id === currentId.value)
  if (found) {
    return found
  }
  // Fallback when backend hasn't loaded yet or server not in list
  return { id: currentId.value, name: currentId.value || 'Unknown', loader: '', version: '', status: 'unknown' }
})

const otherServers = computed(() =>
  store.serversList.filter((s) => s.id !== currentId.value)
)

// runtime.status takes precedence over the persisted top-level status,
// matching the pattern in Servers.vue: `runtime.status || server.status`.
const statusOf = (s) => s?.runtime?.status || s?.status || 'unknown'

const dotColor = (s) => {
  switch (statusOf(s)) {
    case 'running':    return 'var(--success)'
    case 'installing': return 'var(--primary)'
    case 'pending':    return 'var(--warning)'
    case 'failed':     return 'var(--danger)'
    default:           return 'var(--text-disabled)'
  }
}

const metaText = (s) => {
  const loader = s?.loader ? s.loader.charAt(0).toUpperCase() + s.loader.slice(1) : ''
  const version = s?.version || ''
  const status = statusOf(s)
  const parts = [loader && version ? `${loader} ${version}` : loader || version, status].filter(Boolean)
  return parts.join(' · ')
}

const toggle = () => {
  if (!open.value) {
    // Refresh the list when opening the dropdown — covers status changes,
    // creates from /, etc. Don't await: open immediately, list updates
    // reactively when fetch returns.
    store.loadServers()
  }
  open.value = !open.value
}
const close = () => { open.value = false }

const switchTo = (id) => {
  close()
  if (id !== currentId.value) {
    router.push({ name: 'ServerOverview', params: { id } })
  }
}

const goToAddServer = () => {
  close()
  router.push({ name: 'Servers' })
}

const handleDocumentClick = (event) => {
  if (!event.target.closest('.server-switcher')) {
    close()
  }
}

onMounted(() => {
  store.loadServers()
  document.addEventListener('click', handleDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<template>
  <div class="server-switcher">
    <button
      type="button"
      class="server-switcher__trigger"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggle"
    >
      <span class="server-switcher__dot" :style="{ background: dotColor(currentServer) }"></span>
      <span class="server-switcher__info">
        <span class="server-switcher__name">{{ currentServer.name }}</span>
        <span class="server-switcher__meta">{{ metaText(currentServer) }}</span>
      </span>
      <svg class="server-switcher__chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M3 5l3 3 3-3"/>
      </svg>
    </button>

    <div v-if="open" class="server-switcher__dropdown" role="listbox">
      <button
        type="button"
        class="server-switcher__item server-switcher__item--active"
        role="option"
        :aria-selected="true"
        @click="close"
      >
        <span class="server-switcher__dot server-switcher__dot--small" :style="{ background: dotColor(currentServer) }"></span>
        {{ currentServer.name }}
      </button>
      <button
        v-for="s in otherServers"
        :key="s.id"
        type="button"
        class="server-switcher__item"
        role="option"
        :aria-selected="false"
        @click="switchTo(s.id)"
      >
        <span class="server-switcher__dot server-switcher__dot--small" :style="{ background: dotColor(s) }"></span>
        {{ s.name }}
      </button>

      <div class="server-switcher__sep"></div>

      <button
        type="button"
        class="server-switcher__add"
        @click="goToAddServer"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M5.5 1v9M1 5.5h9"/>
        </svg>
        Add server
      </button>
    </div>
  </div>
</template>

<style scoped>
.server-switcher {
  margin: var(--space-2);
  position: relative;
}

.server-switcher__trigger {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease;
}

.server-switcher__trigger:hover {
  border-color: var(--text-disabled);
}

.server-switcher__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.server-switcher__dot--small {
  width: 6px;
  height: 6px;
}

.server-switcher__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.server-switcher__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.server-switcher__meta {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.server-switcher__chevron {
  color: var(--text-disabled);
  flex-shrink: 0;
}

.server-switcher__dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
  z-index: 50;
  box-shadow: var(--shadow-md);
}

.server-switcher__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
}

.server-switcher__item:hover {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.server-switcher__item--active {
  color: var(--text-primary);
}

.server-switcher__sep {
  height: 1px;
  background: var(--border-color);
  margin: 2px 0;
}

.server-switcher__add {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  color: var(--text-disabled);
  font-size: var(--text-xs);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
}

.server-switcher__add:hover {
  color: var(--primary);
}
</style>
