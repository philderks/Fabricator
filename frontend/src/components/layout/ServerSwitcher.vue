<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServerStore } from '../../stores/server'
import { useAuthStore } from '../../stores/auth'
import { useSidebarCollapsed } from '../../composables/useSidebarCollapsed'
import { useMobileNav } from '../../composables/useMobileNav'
import { getEffectiveStatus as statusOf } from '../../utils/getEffectiveStatus'
import { t, te } from '../../i18n'

const route = useRoute()
const router = useRouter()
const store = useServerStore()
const auth = useAuthStore()
const showCreateModal = inject('showCreateModal', ref(false))

const open = ref(false)

const currentId = computed(() => route.params.id)

const currentServer = computed(() => {
  const found = store.serversList.find((s) => s.id === currentId.value)
  if (found) {
    return found
  }
  // Fallback when backend hasn't loaded yet or server not in list
  return { id: currentId.value, name: currentId.value || t('common.unknown'), loader: '', version: '', status: 'unknown' }
})

// Saved order, not current-first: the order shown is the order being edited,
// and the top server is the one the panel opens on (#84).
const orderedServers = computed(() =>
  store.serversList.some((s) => s.id === currentId.value)
    ? store.serversList
    : [currentServer.value, ...store.serversList]
)

const canReorder = computed(() => store.serversList.length > 1)

// Drag to reorder via Pointer Events rather than HTML5 drag-and-drop, which
// never fires on touch. The list reorders live while dragging; one save on drop.
const dragId = ref(null)
let dragMoved = false

const moveServer = (id, toIndex) => {
  const list = [...store.serversList]
  const from = list.findIndex((s) => s.id === id)
  if (from < 0 || from === toIndex || toIndex < 0 || toIndex >= list.length) return false
  list.splice(toIndex, 0, list.splice(from, 1)[0])
  store.serversList = list
  return true
}

const onDragStart = (event, id) => {
  if (event.button !== 0) return
  // Capture keeps move/up on the handle even once the pointer leaves it.
  event.currentTarget.setPointerCapture(event.pointerId)
  dragId.value = id
  dragMoved = false
}

const onDragMove = (event) => {
  if (!dragId.value) return
  const overId = document.elementFromPoint(event.clientX, event.clientY)
    ?.closest('.server-switcher__row')?.dataset.id
  if (!overId || overId === dragId.value) return
  const toIndex = store.serversList.findIndex((s) => s.id === overId)
  if (moveServer(dragId.value, toIndex)) dragMoved = true
}

const onDragEnd = () => {
  if (dragMoved) store.saveServerOrder()
  dragId.value = null
}

// Keyboard fallback on the focused handle.
const onHandleKey = (id, delta) => {
  const from = store.serversList.findIndex((s) => s.id === id)
  if (moveServer(id, from + delta)) store.saveServerOrder()
}

// Status-display logic consolidated in utils/getEffectiveStatus (F6/CC5).
// Historical local fallback was 'unknown' (drift); now uses the util's
// 'pending' default, lockstep with stores/server.js + the backend pin.

// Server icons beside the names. A server without one answers 404; that is
// remembered per icon URL (which carries the store's icon version), so it is
// not asked again on every open, yet a freshly uploaded icon still shows.
const missingIcons = ref(new Set())
const iconFor = (s) => {
  const url = store.iconUrlFor(s.id)
  return missingIcons.value.has(url) ? null : url
}
const markMissing = (s) => missingIcons.value.add(store.iconUrlFor(s.id))
// Rows without an icon keep its space while any row has one, so names line up.
const anyIcon = computed(() => orderedServers.value.some((s) => iconFor(s)))

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
  const raw = statusOf(s)
  const status = te(`switcher.status.${raw}`) ? t(`switcher.status.${raw}`) : raw
  const parts = [loader && version ? `${loader} ${version}` : loader || version, status].filter(Boolean)
  return parts.join(' · ')
}

const { collapsed } = useSidebarCollapsed()
const { isMobile, close: closeDrawer } = useMobileNav()

// The rail treatment is desktop-only, matching AppSidebar's own `isRail`: on
// mobile this sits inside a full-width drawer, where stripping the switcher
// down to a bare status dot would leave the drawer with no indication of which
// server you are looking at.
const isRail = computed(() => collapsed.value && !isMobile.value)

// Railed, the trigger keeps only the status dot, so a title carries the name
// and meta the row would otherwise show.
const triggerTitle = computed(() =>
  isRail.value ? `${currentServer.value.name} — ${metaText(currentServer.value)}` : null
)

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
  // Unlike switchTo, this opens a modal instead of navigating, so the mobile
  // drawer won't be dismissed by AppSidebar's route watcher — and the drawer
  // sits above the modal layer. Dismiss it here.
  closeDrawer()
  // Modal is mounted at App.vue and provided as `showCreateModal`, so this
  // works from any layout (no need to route to "/" first).
  showCreateModal.value = true
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
  <div class="server-switcher" :class="{ 'is-collapsed': isRail }">
    <button
      type="button"
      class="server-switcher__trigger"
      :aria-expanded="open"
      aria-haspopup="true"
      :title="triggerTitle"
      @click="toggle"
    >
      <span class="server-switcher__dot" :style="{ background: dotColor(currentServer) }"></span>
      <img v-if="iconFor(currentServer)" class="server-switcher__icon" :src="iconFor(currentServer)" alt="" @error="markMissing(currentServer)" />
      <span class="server-switcher__info">
        <span class="server-switcher__name">{{ currentServer.name }}</span>
        <span class="server-switcher__meta">{{ metaText(currentServer) }}</span>
      </span>
      <svg class="server-switcher__chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M3 5l3 3 3-3"/>
      </svg>
    </button>

    <div v-if="open" class="server-switcher__dropdown">
      <div
        v-for="s in orderedServers"
        :key="s.id"
        class="server-switcher__row"
        :class="{ 'is-dragging': s.id === dragId }"
        :data-id="s.id"
      >
        <button
          type="button"
          class="server-switcher__item"
          :class="{ 'server-switcher__item--active': s.id === currentId }"
          :aria-current="s.id === currentId ? 'true' : null"
          @click="switchTo(s.id)"
        >
          <span class="server-switcher__dot server-switcher__dot--small" :style="{ background: dotColor(s) }"></span>
          <img v-if="iconFor(s)" class="server-switcher__icon server-switcher__icon--small" :src="iconFor(s)" alt="" @error="markMissing(s)" />
          <span v-else-if="anyIcon" class="server-switcher__icon server-switcher__icon--small" aria-hidden="true"></span>
          {{ s.name }}
        </button>
        <span
          v-if="canReorder"
          class="server-switcher__grip"
          role="button"
          tabindex="0"
          :aria-label="$t('switcher.reorderLabel', { name: s.name })"
          :title="$t('switcher.reorderTitle')"
          @pointerdown="onDragStart($event, s.id)"
          @pointermove="onDragMove"
          @pointerup="onDragEnd"
          @pointercancel="onDragEnd"
          @keydown.up.prevent="onHandleKey(s.id, -1)"
          @keydown.down.prevent="onHandleKey(s.id, 1)"
        >
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor" aria-hidden="true">
            <circle cx="3" cy="2" r="1"/><circle cx="7" cy="2" r="1"/>
            <circle cx="3" cy="6" r="1"/><circle cx="7" cy="6" r="1"/>
            <circle cx="3" cy="10" r="1"/><circle cx="7" cy="10" r="1"/>
          </svg>
        </span>
      </div>

      <div class="server-switcher__sep"></div>

      <button
        v-if="!auth.managed"
        type="button"
        class="server-switcher__add"
        @click="goToAddServer"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M5.5 1v9M1 5.5h9"/>
        </svg>
        {{ $t('switcher.addServer') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.server-switcher {
  margin: var(--space-2);
  position: relative;
}

/* Rail: the status dot is the whole control. The name/meta and chevron are
   dropped outright rather than visually hidden — the trigger's `title` carries
   both, so nothing is lost to assistive tech. */
.server-switcher.is-collapsed .server-switcher__info,
.server-switcher.is-collapsed .server-switcher__chevron,
.server-switcher.is-collapsed .server-switcher__trigger .server-switcher__icon {
  display: none;
}

.server-switcher.is-collapsed .server-switcher__trigger {
  justify-content: center;
  gap: 0;
  padding-left: 0;
  padding-right: 0;
  /* Matches the nav icons' row height so the rail reads as one column. */
  padding-top: 10px;
  padding-bottom: 10px;
}

/* Opens rightward out over the content instead of trying to fit the rail —
   the sidebar no longer clips, so the menu keeps a readable width and the
   switcher stays one click from the rail. */
.server-switcher.is-collapsed .server-switcher__dropdown {
  right: auto;
  min-width: 190px;
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

.server-switcher__icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 3px;
  image-rendering: pixelated;
}

.server-switcher__icon--small {
  width: 18px;
  height: 18px;
  border-radius: 2px;
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

.server-switcher__row {
  display: flex;
  align-items: center;
}

.server-switcher__row:hover {
  background: var(--bg-secondary);
}

.server-switcher__item:hover {
  color: var(--text-secondary);
}

/* Drag handle: revealed on row hover/focus so the list stays quiet, and
   always shown where there is no hover (touch). */
.server-switcher__grip {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-right: var(--space-1);
  border-radius: var(--radius-sm);
  color: var(--text-disabled);
  cursor: grab;
  /* Without this a touch drag scrolls the page instead of the row. */
  touch-action: none;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.server-switcher__row:hover .server-switcher__grip,
.server-switcher__grip:focus-visible,
.server-switcher__row.is-dragging .server-switcher__grip {
  opacity: 1;
}

.server-switcher__grip:hover,
.server-switcher__grip:focus-visible {
  color: var(--text-primary);
  outline: none;
  background: var(--bg-tertiary);
}

.server-switcher__row.is-dragging {
  background: var(--bg-secondary);
  box-shadow: inset 2px 0 0 var(--primary);
}

.server-switcher__row.is-dragging .server-switcher__grip {
  cursor: grabbing;
}

@media (hover: none) {
  .server-switcher__grip {
    opacity: 1;
  }
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
