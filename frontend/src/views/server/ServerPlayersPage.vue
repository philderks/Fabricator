<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import WhitelistPanel from '../../components/players/WhitelistPanel.vue'
import OpsPanel from '../../components/players/OpsPanel.vue'
import BansPanel from '../../components/players/BansPanel.vue'
import KnownPlayersPanel from '../../components/players/KnownPlayersPanel.vue'
import StatCard from '../../components/ui/StatCard.vue'
import AppButton from '../../components/ui/AppButton.vue'
import { usePlayersStore } from '../../stores/players'
import { useServerStore } from '../../stores/server'
import { useToast } from '../../composables/useToast'

const store = usePlayersStore()
const serverStore = useServerStore()
const toast = useToast()

onMounted(async () => {
  await store.loadAll()
  if (store.isRunning) store.startOnlinePolling()
})

onUnmounted(() => {
  store.stopOnlinePolling()
})

watch(
  () => serverStore.currentServerId,
  (id, oldId) => {
    if (!id || id === oldId) return
    store.stopOnlinePolling()
    store.resetState()
    store.loadAll().then(() => {
      if (store.isRunning) store.startOnlinePolling()
    })
  }
)

watch(
  () => store.isRunning,
  (running) => {
    if (running) store.startOnlinePolling()
    else store.stopOnlinePolling()
  }
)

// ── Tab state ──────────────────────────────────────────────────────────────
const activeTab = ref('all')

// ── All Players tab ────────────────────────────────────────────────────────
const filter = ref('ALL')
const search = ref('')

const onlineNames = computed(() => new Set(store.online.map(p => p.name.toLowerCase())))
const opMap = computed(() => new Map(store.ops.map(o => [o.name.toLowerCase(), o])))
const bannedSet = computed(() => new Set(store.bans.map(b => b.name.toLowerCase())))

function lastSeenFromExpiresOn(expiresOn) {
  if (!expiresOn) return null
  // Minecraft caches UUID for 30 days from last login; subtract to approximate last-seen
  return new Date(new Date(expiresOn).getTime() - 30 * 24 * 60 * 60 * 1000)
}

function relativeTime(date) {
  if (!date) return ''
  const m = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000))
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const allPlayers = computed(() => {
  const players = store.knownPlayers.map(p => {
    const key = (p.name || '').toLowerCase()
    const op = opMap.value.get(key)
    return {
      name: p.name,
      uuid: p.uuid,
      isOnline: onlineNames.value.has(key),
      lastSeen: lastSeenFromExpiresOn(p.expiresOn),
      isOp: !!op,
      opLevel: op?.level ?? 4,
      isBanned: bannedSet.value.has(key),
    }
  })
  return players.sort((a, b) => {
    if (a.isOnline !== b.isOnline) return a.isOnline ? -1 : 1
    return (b.lastSeen?.getTime() ?? 0) - (a.lastSeen?.getTime() ?? 0)
  })
})

const filteredPlayers = computed(() => {
  let list = allPlayers.value
  if (filter.value === 'ONLINE') list = list.filter(p => p.isOnline)
  else if (filter.value === 'OPS') list = list.filter(p => p.isOp)
  else if (filter.value === 'BANNED') list = list.filter(p => p.isBanned)
  const q = search.value.trim().toLowerCase()
  return q ? list.filter(p => p.name.toLowerCase().includes(q)) : list
})

const onlineCount = computed(() => store.online.length)
const knownCount = computed(() => store.knownPlayers.length)
const oldestSeen = computed(() => {
  let oldest = null
  for (const p of store.knownPlayers) {
    const d = lastSeenFromExpiresOn(p.expiresOn)
    if (d && (!oldest || d < oldest)) oldest = d
  }
  return oldest ? relativeTime(oldest) : '—'
})

function initials(name) {
  return (name || '').slice(0, 2).toUpperCase() || '?'
}

async function safe(fn) {
  try { await fn() } catch (e) { toast.error(e.message || 'Operation failed') }
}

// ── Kick with reason ───────────────────────────────────────────────────────
const kickTarget = ref(null)  // player name being kicked
const kickReason = ref('')

function startKick(name) {
  kickTarget.value = name
  kickReason.value = ''
}

async function executeKick(name) {
  await safe(() => store.kick(name, kickReason.value.trim() || null))
  kickTarget.value = null
  kickReason.value = ''
}
</script>

<template>
  <div class="players-page">
    <div v-if="!store.onlineMode" class="players-page__offline-banner" role="status">
      Server is in offline mode — player avatars and online identity verification are unavailable.
    </div>

    <div class="players-tabs" role="tablist">
      <button
        v-for="tab in [{ id: 'all', label: 'All Players' }, { id: 'whitelist', label: 'Whitelist' }, { id: 'operators', label: 'Operators' }, { id: 'banned', label: 'Banned' }]"
        :key="tab.id"
        :class="['players-tab', { 'players-tab--active': activeTab === tab.id }]"
        role="tab"
        :aria-selected="activeTab === tab.id"
        type="button"
        @click="activeTab = tab.id"
      >{{ tab.label }}</button>
    </div>

    <!-- All Players tab -->
    <div v-if="activeTab === 'all'" class="players-tab-content">
      <div class="players-stats">
        <StatCard label="Online now" :value="onlineCount" accent="success" />
        <StatCard label="Known players" :value="knownCount" />
        <StatCard label="Oldest seen" :value="oldestSeen" />
      </div>

      <div class="players-toolbar">
        <div class="players-filters">
          <button
            v-for="f in ['ALL', 'ONLINE', 'OPS', 'BANNED']"
            :key="f"
            :class="['filter-pill', { 'filter-pill--active': filter === f }]"
            type="button"
            @click="filter = f"
          >{{ f }}</button>
        </div>
        <input v-model="search" class="players-search" type="search" placeholder="Search players…" />
      </div>

      <ul class="all-players-list">
        <li v-for="p in filteredPlayers" :key="p.uuid || p.name" class="all-player-row">
          <span :class="['status-dot', p.isOnline ? 'status-dot--online' : 'status-dot--offline']" />
          <span :class="['initials-av', p.isOnline ? 'initials-av--online' : '']">{{ initials(p.name) }}</span>
          <div class="all-player-row__main">
            <span class="all-player-row__name">{{ p.name }}</span>
            <span class="all-player-row__when">{{ p.isOnline ? 'online' : relativeTime(p.lastSeen) }}</span>
          </div>
          <span v-if="p.isOp" class="role-badge role-badge--op">OP L{{ p.opLevel }}</span>
          <span v-else-if="p.isBanned" class="role-badge role-badge--banned">Banned</span>
          <div class="all-player-row__actions">
            <template v-if="p.isOnline && kickTarget === p.name">
              <input
                v-model="kickReason"
                class="kick-reason-input"
                type="text"
                placeholder="Kick reason…"
                maxlength="256"
                @keydown.enter.prevent="executeKick(p.name)"
                @keydown.escape="kickTarget = null"
              />
              <AppButton variant="danger" size="sm" @click="executeKick(p.name)">Kick</AppButton>
              <AppButton variant="ghost" size="sm" @click="kickTarget = null">✕</AppButton>
            </template>
            <AppButton v-else-if="p.isOnline" variant="ghost" size="sm" @click="startKick(p.name)">Kick</AppButton>
            <AppButton v-if="p.isBanned" variant="ghost" size="sm" @click="safe(() => store.removeBan(p.name))">Unban</AppButton>
            <AppButton v-else variant="danger" size="sm" @click="safe(() => store.addBan(p.name, null))">Ban</AppButton>
          </div>
        </li>
        <li v-if="!filteredPlayers.length" class="players-empty">No players found.</li>
      </ul>
    </div>

    <template v-else-if="activeTab === 'whitelist'">
      <WhitelistPanel />
      <KnownPlayersPanel />
    </template>
    <template v-else-if="activeTab === 'operators'">
      <OpsPanel />
      <KnownPlayersPanel />
    </template>
    <template v-else-if="activeTab === 'banned'">
      <BansPanel />
      <KnownPlayersPanel />
    </template>
  </div>
</template>

<style scoped>
.players-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.players-page__offline-banner {
  padding: var(--space-2) var(--space-3);
  background: rgba(249, 115, 22, 0.08);
  border: 1px solid rgba(249, 115, 22, 0.3);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

/* ── Tab nav ── */
.players-tabs {
  display: flex;
  gap: var(--space-1);
  border-bottom: 1px solid var(--border-color);
}

.players-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  padding: var(--space-2) var(--space-3);
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.players-tab:hover {
  color: var(--text-secondary);
}

.players-tab--active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

/* ── All Players tab ── */
.players-tab-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.players-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}

.players-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.players-filters {
  display: flex;
  gap: var(--space-1);
}

.filter-pill {
  height: 26px;
  padding: 0 var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.filter-pill:hover {
  color: var(--text-secondary);
}

.filter-pill--active {
  background: rgba(249, 115, 22, 0.12);
  border-color: var(--primary);
  color: var(--primary);
}

.players-search {
  height: 32px;
  flex: 1;
  max-width: 220px;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
}

.players-search:focus {
  outline: none;
  border-color: var(--primary);
}

.all-players-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.all-player-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}

.all-player-row:last-child {
  border-bottom: none;
}

.all-player-row__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.all-player-row__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.all-player-row__when {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  font-family: var(--font-mono);
}

.all-player-row__actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.all-player-row:hover .all-player-row__actions {
  opacity: 1;
}

/* ── Status dot ── */
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot--online  { background: var(--success); }
.status-dot--offline { background: var(--text-disabled); }

/* ── Initials avatar ── */
.initials-av {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--text-muted);
}

.initials-av--online {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.3);
  color: var(--success);
}

/* ── Role badge ── */
.role-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 1px var(--space-2);
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}

.role-badge--op     { background: rgba(249, 115, 22, 0.12); color: var(--primary); }
.role-badge--banned { background: rgba(239, 68, 68, 0.12);  color: var(--danger); }

.players-empty {
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--text-disabled);
}

/* ── Inline kick reason input ── */
.kick-reason-input {
  height: 26px;
  width: 140px;
  padding: 0 var(--space-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-xs);
}
.kick-reason-input:focus { outline: none; border-color: var(--danger); }
</style>
