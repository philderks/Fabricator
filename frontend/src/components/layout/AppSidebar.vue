<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ServerSwitcher from './ServerSwitcher.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { useAuthStore } from '../../stores/auth'
import { version as appVersion } from '../../../package.json'
import { getUpdateStatus, triggerUpdate } from '../../api/servers'
import { useToast } from '../../composables/useToast'
import { useServerStore } from '../../stores/server'
import { loaderContentKind, contentLabel } from '../../utils/loaderKind'

const route = useRoute()
const toast = useToast()
const store = useServerStore()
const showCreateModal = inject('showCreateModal', ref(false))

const auth = useAuthStore()
const router = useRouter()

async function onLock() {
  await auth.logout()
  router.push({ name: 'Login' })
}

const serverId = computed(() => route.params.id)
const hasServerContext = computed(() => Boolean(serverId.value))

const ALL_NAV_ITEMS = [
  { name: 'ServerOverview', label: 'Overview', icon: 'overview' },
  { name: 'ServerConsole',  label: 'Console',  icon: 'console'  },
  { name: 'ServerPlayers',  label: 'Players',  icon: 'players'  },
  { name: 'ServerMods',     label: 'Mods',     icon: 'mods'     },
  { name: 'ServerFiles',    label: 'Files',    icon: 'files'    },
  { name: 'ServerBackups',  label: 'Backups',  icon: 'backups'  },
  { name: 'ServerPlayit',   label: 'playit.gg', icon: 'network' },
  { name: 'ServerSettings', label: 'Properties', icon: 'properties' }
]

// Nav entries hidden under managed mode (surfaces the fleet gate denies).
const MANAGED_HIDDEN_NAV = new Set(['ServerBackups', 'ServerPlayit'])

// The add-on tab (ServerMods) is hidden for Vanilla (no add-on surface) and
// relabelled "Plugins" for Bukkit-family loaders (Paper/Purpur/Folia/Pufferfish),
// which install plugins rather than mods. The route name/path stay 'ServerMods'.
const navItems = computed(() => {
  const loader = store.server?.loader
  const kind = loaderContentKind(loader)
  const base = auth.managed
    ? ALL_NAV_ITEMS.filter(item => !MANAGED_HIDDEN_NAV.has(item.name))
    : ALL_NAV_ITEMS
  if (kind === 'none') {
    return base.filter(item => item.name !== 'ServerMods')
  }
  return base.map(item =>
    item.name === 'ServerMods'
      ? { ...item, label: contentLabel(loader) }
      : item
  )
})

// ---------- Update polling (relocated from Servers.vue) ----------
const POLL_INTERVAL_IDLE = 15 * 60 * 1000   // 15 min — avoid hammering GitHub API
const POLL_INTERVAL_ACTIVE = 4_000           // 4 s while an update is running

const updateState = ref({
  inProgress: false,
  currentVersion: appVersion,
  latestVersion: null,
  updateAvailable: false,
  selfUpdateDisabled: false,
  lastError: null,
  lastExitCode: null
})
const updateTriggering = ref(false)
/** 0 idle, 1 armed after trigger, 2 saw inProgress true (avoids toast if job never starts). */
const updateOutcomeWatch = ref(0)
// setTimeout handle (was setInterval + recursive-rearm, which created a
// fresh interval on every fire — wasteful and made the "double-mount" claim
// in F7 hard to reason about). Switched to setTimeout-recursive so one
// timer is in flight at any moment.
let updateStatusTimeoutId = null

watch(
  () => updateState.value.inProgress,
  (inProg) => {
    if (updateOutcomeWatch.value === 1 && inProg) {
      updateOutcomeWatch.value = 2
    }
    if (updateOutcomeWatch.value === 2 && !inProg) {
      updateOutcomeWatch.value = 0
      const { lastExitCode, lastError } = updateState.value
      if (lastExitCode === 0) {
        toast.success(
          'Update finished. Refresh the page if it does not reload automatically.',
          'Fabricator Update'
        )
      } else {
        const detail =
          lastError || (lastExitCode != null ? `Exit code ${lastExitCode}` : 'Update failed')
        toast.error(detail, 'Fabricator Update')
      }
    }
  }
)

const loadUpdateState = async () => {
  try {
    updateState.value = await getUpdateStatus()
  } catch (error) {
    // Silent — the pill is non-critical UI; surfacing a toast on every
    // poll failure would be noisy.
    console.error('Failed to load update status:', error)
  }
}

const scheduleNextPoll = () => {
  if (updateStatusTimeoutId) clearTimeout(updateStatusTimeoutId)
  const interval = updateState.value.inProgress ? POLL_INTERVAL_ACTIVE : POLL_INTERVAL_IDLE
  updateStatusTimeoutId = setTimeout(async () => {
    await loadUpdateState()
    scheduleNextPoll()
  }, interval)
}

const stopUpdatePoll = () => {
  if (updateStatusTimeoutId) {
    clearTimeout(updateStatusTimeoutId)
    updateStatusTimeoutId = null
  }
}

const updateAvailable = computed(() =>
  Boolean(updateState.value.updateAvailable) &&
  !updateState.value.inProgress &&
  !updateState.value.selfUpdateDisabled
)

const updateLabel = computed(() => {
  if (updateState.value.selfUpdateDisabled) return 'Managed by image'
  if (updateState.value.inProgress || updateTriggering.value) return 'Updating…'
  if (updateAvailable.value) return 'Update available'
  return 'Up to date'
})

const updateVersionLabel = computed(() => {
  const v = updateState.value.currentVersion || appVersion
  return v ? String(v) : ''
})

// In-app modal-based confirm (CC6: no window.confirm). The runUpdate flow
// is the only consumer here, so we keep state local instead of pushing it
// into the store — the promise-resolve pattern lets us preserve the
// `await confirmed` shape of the original window.confirm call.
const showUpdateConfirm = ref(false)
let updateConfirmResolver = null

const requestUpdateConfirmation = () => new Promise((resolve) => {
  updateConfirmResolver = resolve
  showUpdateConfirm.value = true
})

const handleUpdateConfirm = () => {
  showUpdateConfirm.value = false
  if (updateConfirmResolver) {
    updateConfirmResolver(true)
    updateConfirmResolver = null
  }
}

const handleUpdateCancel = () => {
  showUpdateConfirm.value = false
  if (updateConfirmResolver) {
    updateConfirmResolver(false)
    updateConfirmResolver = null
  }
}

const runUpdate = async () => {
  if (!updateAvailable.value || updateTriggering.value) return
  const confirmed = await requestUpdateConfirmation()
  if (!confirmed) return

  updateTriggering.value = true
  try {
    const result = await triggerUpdate()
    if (result.started) {
      updateOutcomeWatch.value = 1
      toast.success('Update started in background', 'Fabricator Update')
      await loadUpdateState()
      scheduleNextPoll()
    } else {
      toast.error(result.error || 'Unable to start update', 'Fabricator Update')
    }
  } catch (error) {
    console.error('Failed to trigger update:', error)
    toast.error(error.message || 'Failed to trigger update', 'Fabricator Update')
  } finally {
    updateTriggering.value = false
  }
}

onMounted(async () => {
  await loadUpdateState()
  scheduleNextPoll()
})

onUnmounted(() => {
  stopUpdatePoll()
  if (updateConfirmResolver) {
    updateConfirmResolver(false)
    updateConfirmResolver = null
  }
})
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__logo">
      <img
        class="app-sidebar__logo-img"
        src="/favicon.svg"
        alt=""
        width="24"
        height="24"
        aria-hidden="true"
      />
      <span class="app-sidebar__brand">Fabricator</span>
    </div>

    <ServerSwitcher v-if="hasServerContext" />
    <button
      v-else-if="!auth.managed"
      type="button"
      class="app-sidebar__no-server-chip"
      @click="showCreateModal = true"
    >
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M5.5 1v9M1 5.5h9"/>
      </svg>
      <span>No servers yet</span>
    </button>

    <nav class="app-sidebar__nav" aria-label="Server navigation">
      <component
        :is="hasServerContext ? 'router-link' : 'div'"
        v-for="item in navItems"
        :key="item.name"
        v-bind="hasServerContext
          ? { to: { name: item.name, params: { id: serverId } }, activeClass: 'is-active' }
          : { 'aria-disabled': 'true' }"
        class="app-sidebar__nav-item"
        :class="{ 'app-sidebar__nav-item--ghost': !hasServerContext }"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <template v-if="item.icon === 'overview'">
            <rect x="1.5" y="1.5" width="4.5" height="4.5" rx="1"/>
            <rect x="9" y="1.5" width="4.5" height="4.5" rx="1"/>
            <rect x="1.5" y="9" width="4.5" height="4.5" rx="1"/>
            <rect x="9" y="9" width="4.5" height="4.5" rx="1"/>
          </template>
          <template v-else-if="item.icon === 'console'">
            <rect x="1" y="2" width="13" height="11" rx="1.5"/>
            <path d="M4 5.5l2.5 2L4 9.5"/>
            <path d="M8 9.5h3"/>
          </template>
          <template v-else-if="item.icon === 'players'">
            <circle cx="7.5" cy="5" r="2.5" />
            <path d="M3 13c0-2.5 2-4.5 4.5-4.5S12 10.5 12 13" />
          </template>
          <template v-else-if="item.icon === 'mods'">
            <path d="M7.5 1L13 4.5v6L7.5 14 2 10.5v-6L7.5 1z"/>
            <path d="M7.5 1v13M2 4.5l5.5 3.5 5.5-3.5"/>
          </template>
          <template v-else-if="item.icon === 'files'">
            <path d="M2 3.5A1.5 1.5 0 013.5 2h3l1.5 2H12a1.5 1.5 0 011.5 1.5v7A1.5 1.5 0 0112 14H3.5A1.5 1.5 0 012 12.5v-9z"/>
          </template>
          <template v-else-if="item.icon === 'backups'">
            <rect x="1.5" y="3" width="12" height="3" rx="0.6"/>
            <path d="M2.5 6v6.5A1 1 0 003.5 13.5h8A1 1 0 0012.5 12.5V6"/>
            <path d="M6 8.5h3"/>
          </template>
          <template v-else-if="item.icon === 'network'">
            <circle cx="7.5" cy="7.5" r="6"/>
            <path d="M1.5 7.5h12"/>
            <path d="M7.5 1.5c1.85 1.7 2.85 3.85 2.85 6s-1 4.3-2.85 6c-1.85-1.7-2.85-3.85-2.85-6s1-4.3 2.85-6z"/>
          </template>
          <template v-else-if="item.icon === 'properties'">
            <path d="M2 4h7"/>
            <path d="M13 4h-2"/>
            <circle cx="10" cy="4" r="1.6"/>
            <path d="M2 11h2"/>
            <path d="M13 11H6"/>
            <circle cx="5" cy="11" r="1.6"/>
          </template>
        </svg>
        <span>{{ item.label }}</span>
      </component>
    </nav>

    <div class="app-sidebar__bottom">
      <component
        :is="hasServerContext ? 'router-link' : 'div'"
        v-bind="hasServerContext
          ? { to: { name: 'ServerGeneralSettings', params: { id: serverId } }, activeClass: 'is-active' }
          : { 'aria-disabled': 'true' }"
        class="app-sidebar__nav-item"
        :class="{ 'app-sidebar__nav-item--ghost': !hasServerContext }"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M11.5 8.9L13.4 8.9L13.4 6.2L11.5 6.1L10.7 4.8L11.6 3.1L9.3 1.8L8.2 3.4L6.8 3.4L5.8 1.8L3.4 3.1L4.3 4.8L3.6 6.1L1.7 6.2L1.7 8.9L3.6 8.9L4.3 10.2L3.4 11.9L5.8 13.2L6.8 11.6L8.2 11.6L9.3 13.2L11.6 11.9L10.7 10.2Z"/>
          <circle cx="7.5" cy="7.5" r="2.2"/>
        </svg>
        <span>Settings</span>
      </component>

      <button
        v-if="auth.enabled"
        type="button"
        class="app-sidebar__nav-item app-sidebar__account-btn"
        @click="onLock"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <rect x="3.5" y="6.8" width="8" height="6" rx="1"/>
          <path d="M5.3 6.8V4.8a2.2 2.2 0 014.4 0v2"/>
        </svg>
        <span>Lock</span>
      </button>

      <component
        :is="updateAvailable ? 'button' : 'div'"
        :type="updateAvailable ? 'button' : undefined"
        class="app-sidebar__update-pill"
        :class="{ 'is-clickable': updateAvailable }"
        :disabled="updateAvailable && updateTriggering ? true : undefined"
        @click="updateAvailable ? runUpdate() : undefined"
      >
        <span
          class="app-sidebar__update-dot"
          :class="updateAvailable ? 'is-available' : 'is-idle'"
          aria-hidden="true"
        ></span>
        <span class="app-sidebar__update-text">{{ updateLabel }}</span>
        <span class="app-sidebar__update-ver">{{ updateVersionLabel }}</span>
      </component>
    </div>

    <ConfirmModal
      :show="showUpdateConfirm"
      title="Run Fabricator update?"
      message="Run Fabricator update now?"
      description="The service may restart briefly while preserving server data and config."
      type="warning"
      confirm-text="Run update"
      cancel-text="Cancel"
      @confirm="handleUpdateConfirm"
      @cancel="handleUpdateCancel"
    />
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  min-height: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: var(--app-chrome-header-height);
  padding: var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.app-sidebar__logo-img {
  flex-shrink: 0;
  display: block;
}

.app-sidebar__brand {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

/* "No servers yet" chip — replaces ServerSwitcher when no server context */
.app-sidebar__no-server-chip {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 10px var(--space-2) var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: #181818;
  border: 1px dashed #272727;
  border-radius: var(--radius-md);
  color: #333;
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.app-sidebar__no-server-chip:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.app-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2);
  flex: 1;
}

.app-sidebar__nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}

.app-sidebar__nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.app-sidebar__nav-item.is-active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.app-sidebar__nav-item.is-active .app-sidebar__nav-icon {
  color: var(--primary);
}

/* Dimmed, non-interactive nav items shown when no server is selected. */
.app-sidebar__nav-item--ghost,
.app-sidebar__nav-item--ghost:hover {
  color: #2a2a2a;
  background: transparent;
  cursor: default;
}

.app-sidebar__nav-icon {
  flex-shrink: 0;
}

.app-sidebar__bottom {
  padding: var(--space-2);
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Account actions styled like nav items but they're <button>s. */
.app-sidebar__account-btn {
  background: none;
  border: none;
  width: 100%;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

/* Update status pill — subtle, blends into the sidebar */
.app-sidebar__update-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  background: #181818;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: inherit;
  font-family: inherit;
  text-align: left;
  width: 100%;
  transition: border-color 0.15s ease;
}

.app-sidebar__update-pill.is-clickable {
  cursor: pointer;
}

.app-sidebar__update-pill:hover {
  border-color: #2a2a2a;
}

.app-sidebar__update-pill:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.app-sidebar__update-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.app-sidebar__update-dot.is-idle {
  background: var(--success);
}

.app-sidebar__update-dot.is-available {
  background: var(--primary);
}

.app-sidebar__update-text {
  flex: 1;
  font-size: var(--text-xs);
  color: #3a3a3a;
}

.app-sidebar__update-ver {
  font-size: 10px;
  color: #2e2e2e;
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}
</style>
