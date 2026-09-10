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
import { useSidebarCollapsed } from '../../composables/useSidebarCollapsed'
import { useMobileNav } from '../../composables/useMobileNav'
import { loaderContentKind, contentLabel } from '../../utils/loaderKind'

const { collapsed, toggle: toggleCollapsed } = useSidebarCollapsed()
const { isMobile, drawerOpen, close: closeDrawer } = useMobileNav()

// The rail and the drawer are mutually exclusive presentations of the same
// sidebar: on mobile the whole thing is off-canvas at full width, so a collapse
// preference set on desktop must not shrink it to an icon strip there. The CSS
// side of this pairing lives in global.css (--sidebar-width goes to 0 on
// mobile) and in the media block below.
const isRail = computed(() => collapsed.value && !isMobile.value)

// Collapsed, labels are visually hidden but stay in the DOM for screen readers,
// so `title` is only a mouse affordance. Native tooltips rather than styled
// ones on purpose: __nav scrolls, and `overflow-y: auto` computes overflow-x to
// `auto` too, so a tooltip drawn outside the rail would be clipped there.
// Mouse-only by nature, so the drawer never gets them.
const railTitle = (label) => (isRail.value ? label : null)

// One button, two jobs: it collapses the rail on desktop and dismisses the
// drawer on mobile, where "narrower" isn't a state the sidebar has.
const onCollapseClick = () => {
  if (isMobile.value) closeDrawer()
  else toggleCollapsed()
}

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

// Every nav item in here is a link, so a tap that navigates has done what the
// drawer was opened for. Watching the resolved path (not route.name) also
// covers switching servers, which keeps the name and changes only the param.
watch(() => route.fullPath, () => closeDrawer())

// Opening a modal from the drawer is the one action that doesn't navigate, so
// it has to dismiss the drawer itself — the drawer sits above the modal layer.
const openCreateModal = () => {
  closeDrawer()
  showCreateModal.value = true
}

const settingsTarget = computed(() =>
  hasServerContext.value
    ? { name: 'ServerGeneralSettings', params: { id: serverId.value } }
    : { name: 'GlobalSettings' }
)

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
  // Managed: the self-update probe is gate-denied (silent recurring 403); do
  // not fetch or arm either poll cadence.
  if (auth.managed) return
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
  <!-- Drawer scrim. Rendered on mobile only, and always — not v-if'd on
       drawerOpen — so it can fade rather than pop in. -->
  <div
    v-if="isMobile"
    class="app-sidebar__scrim"
    :class="{ 'is-visible': drawerOpen }"
    aria-hidden="true"
    @click="closeDrawer"
  ></div>

  <aside
    id="app-sidebar"
    class="app-sidebar"
    :class="{ 'is-collapsed': isRail, 'is-drawer-open': drawerOpen }"
  >
    <!-- Sits on the seam it controls, at header-row height: where the eye lands
         first, and directly on the boundary that moves. Straddling the border
         instead of sitting inside the rail is what keeps it in one place across
         both states — it shifts horizontally with the edge and nothing else,
         and it leaves the narrow rail's header free for the logo. -->
    <button
      type="button"
      class="app-sidebar__collapse-btn"
      :aria-label="isMobile ? 'Close navigation menu' : (collapsed ? 'Expand sidebar' : 'Collapse sidebar')"
      :aria-expanded="isMobile ? drawerOpen : !collapsed"
      :title="isMobile ? 'Close menu' : (collapsed ? 'Expand sidebar' : 'Collapse sidebar')"
      @click="onCollapseClick"
    >
      <svg
        class="app-sidebar__collapse-icon"
        width="12" height="12" viewBox="0 0 12 12"
        fill="none" stroke="currentColor" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
      >
        <path d="M7.5 2.5l-4 3.5 4 3.5"/>
      </svg>
    </button>

    <!-- The way back to the server list. RootLayout routes (Servers, the
         server-less Settings) have no topbar and no ServerSwitcher, so without
         this the only exit from them is the browser's back button. -->
    <router-link
      :to="{ name: 'Servers' }"
      class="app-sidebar__logo"
      :title="railTitle('Fabricator — all servers')"
    >
      <img
        class="app-sidebar__logo-img"
        src="/favicon.svg"
        alt=""
        width="24"
        height="24"
        aria-hidden="true"
      />
      <span class="app-sidebar__brand app-sidebar__label">Fabricator</span>
    </router-link>

    <ServerSwitcher v-if="hasServerContext" />
    <button
      v-else-if="!auth.managed"
      type="button"
      class="app-sidebar__no-server-chip"
      :title="railTitle('No servers yet — create one')"
      @click="openCreateModal"
    >
      <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M5.5 1v9M1 5.5h9"/>
      </svg>
      <span class="app-sidebar__label">No servers yet</span>
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
        :title="railTitle(item.label)"
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
            <circle cx="7.5" cy="4.5" r="3" />
            <path d="M2 13.5c0-3 2.46-5.5 5.5-5.5s5.5 2.5 5.5 5.5" />
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
            <path d="M2 2.5h7"/>
            <path d="M13 2.5h-2"/>
            <circle cx="10" cy="2.5" r="1.8"/>
            <path d="M2 12.5h2"/>
            <path d="M13 12.5H6"/>
            <circle cx="5" cy="12.5" r="1.8"/>
          </template>
        </svg>
        <span class="app-sidebar__label">{{ item.label }}</span>
      </component>
    </nav>

    <div class="app-sidebar__bottom">
      <!-- Unlike the server nav above, Settings is never ghosted: most of what
           it holds (Java, MCP, password, display) is panel-wide, so it falls
           back to the server-less /settings route. -->
      <router-link
        :to="settingsTarget"
        active-class="is-active"
        class="app-sidebar__nav-item"
        :title="railTitle('Settings')"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M11.5 8.9L13.4 8.9L13.4 6.2L11.5 6.1L10.7 4.8L11.6 3.1L9.3 1.8L8.2 3.4L6.8 3.4L5.8 1.8L3.4 3.1L4.3 4.8L3.6 6.1L1.7 6.2L1.7 8.9L3.6 8.9L4.3 10.2L3.4 11.9L5.8 13.2L6.8 11.6L8.2 11.6L9.3 13.2L11.6 11.9L10.7 10.2Z"/>
          <circle cx="7.5" cy="7.5" r="2.2"/>
        </svg>
        <span class="app-sidebar__label">Settings</span>
      </router-link>

      <button
        v-if="auth.enabled"
        type="button"
        class="app-sidebar__nav-item app-sidebar__account-btn"
        :title="railTitle('Lock')"
        @click="onLock"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <rect x="3.5" y="6.8" width="8" height="6" rx="1"/>
          <path d="M5.3 6.8V4.8a2.2 2.2 0 014.4 0v2"/>
        </svg>
        <span class="app-sidebar__label">Lock</span>
      </button>

      <component
        v-if="!auth.managed"
        :is="updateAvailable ? 'button' : 'div'"
        :type="updateAvailable ? 'button' : undefined"
        class="app-sidebar__update-pill"
        :class="{ 'is-clickable': updateAvailable }"
        :disabled="updateAvailable && updateTriggering ? true : undefined"
        :title="railTitle(`${updateLabel} · ${updateVersionLabel}`)"
        @click="updateAvailable ? runUpdate() : undefined"
      >
        <span
          class="app-sidebar__update-dot"
          :class="updateAvailable ? 'is-available' : 'is-idle'"
          aria-hidden="true"
        ></span>
        <span class="app-sidebar__update-text app-sidebar__label">{{ updateLabel }}</span>
        <span class="app-sidebar__update-ver app-sidebar__label">{{ updateVersionLabel }}</span>
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
  /* Anchor for the collapse handle. Overflow is deliberately visible so that
     handle can straddle the right border; scrolling moved to __nav, which is
     the only part that can outgrow the viewport anyway — a bonus being that
     the logo row and bottom group now stay put instead of scrolling away. */
  position: relative;
  overflow: visible;
  /* The token itself changes on collapse, so both track it. */
  transition: width 0.18s ease, min-width 0.18s ease;
}

.app-sidebar__collapse-btn {
  position: absolute;
  /* Centred on the header row, and on the border itself. */
  top: calc((var(--app-chrome-header-height) - 24px) / 2);
  right: -12px;
  z-index: 30;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 50%;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.app-sidebar__collapse-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.app-sidebar__collapse-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.app-sidebar__collapse-icon {
  transition: transform 0.18s ease;
}

.app-sidebar.is-collapsed .app-sidebar__collapse-icon {
  transform: rotate(180deg);
}

/* ---------- Collapsed (icon-only rail) ---------- */

/* Labels are hidden from sight but kept for assistive tech, so every nav item
   still has an accessible name in the rail — `display: none` would strip it and
   leave a row of unnamed icons. */
.app-sidebar.is-collapsed .app-sidebar__label {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  white-space: nowrap;
  clip-path: inset(50%);
}

.app-sidebar.is-collapsed .app-sidebar__logo,
.app-sidebar.is-collapsed .app-sidebar__nav-item,
.app-sidebar.is-collapsed .app-sidebar__no-server-chip,
.app-sidebar.is-collapsed .app-sidebar__update-pill {
  justify-content: center;
  gap: 0;
  padding-left: 0;
  padding-right: 0;
}

/* Keeps the hit target square rather than letting it collapse onto the icon. */
.app-sidebar.is-collapsed .app-sidebar__update-pill {
  padding-top: 9px;
  padding-bottom: 9px;
}

/* ---------- Mobile (off-canvas drawer) ----------
 *
 * See global.css for the token half of this: --sidebar-width drops to 0 below
 * the same 768px threshold, so the sidebar's slot in the layout closes up and
 * the drawer floats over the content instead of displacing it.
 *
 * z-index sits above the modal layer (1000) on purpose — the drawer is the
 * frontmost surface while it's open, and the two actions in it that would open
 * a modal (create server, run update) dismiss it first or live inside it.
 */
@media (max-width: 768px) {
  .app-sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 1100;
    width: var(--sidebar-width-drawer);
    min-width: var(--sidebar-width-drawer);
    max-width: 85vw;
    box-shadow: var(--shadow-lg);
    transform: translateX(-100%);
    /* Pulled out of the tab order while closed — an off-screen sidebar that
       still takes focus is the classic drawer accessibility bug. Delayed on the
       way out so it doesn't vanish mid-slide. */
    visibility: hidden;
    transition: transform 0.22s ease, visibility 0s linear 0.22s;
  }

  .app-sidebar.is-drawer-open {
    transform: translateX(0);
    visibility: visible;
    transition: transform 0.22s ease, visibility 0s;
  }

  /* Roomier rows for thumbs; the desktop 7px is a pointer-sized target. */
  .app-sidebar__nav-item {
    padding: 11px var(--space-3);
  }

  .app-sidebar__collapse-btn {
    /* Inside the drawer rather than straddling its edge: the edge is over the
       scrim here, where a 24px circle is easy to miss and easy to mistake for
       part of the page behind it. */
    top: calc((var(--app-chrome-header-height) - 28px) / 2);
    right: var(--space-2);
    width: 28px;
    height: 28px;
  }
}

.app-sidebar__scrim {
  position: fixed;
  inset: 0;
  /* One below the drawer, above everything else. */
  z-index: 1099;
  background: rgba(0, 0, 0, 0.6);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.22s ease;
}

.app-sidebar__scrim.is-visible {
  opacity: 1;
  pointer-events: auto;
}

@media (prefers-reduced-motion: reduce) {
  .app-sidebar,
  .app-sidebar.is-drawer-open,
  .app-sidebar__scrim,
  .app-sidebar__collapse-icon {
    transition: none;
  }
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: var(--app-chrome-header-height);
  padding: var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  text-decoration: none;
}

.app-sidebar__logo:hover .app-sidebar__brand {
  color: var(--primary);
}

.app-sidebar__logo:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.app-sidebar__logo-img {
  flex-shrink: 0;
  display: block;
}

.app-sidebar__brand {
  /* Wordmark, not a nav label — it carries the header row next to a 24px mark,
     so it sits a step above the --text-sm used for the items below it. */
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  transition: color 0.15s ease;
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
  /* min-height is what lets a flex child actually shrink below its content and
     scroll, rather than pushing the bottom group off-screen. */
  min-height: 0;
  overflow-y: auto;
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
