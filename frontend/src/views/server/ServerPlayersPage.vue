<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import IpBansPanel from '../../components/players/IpBansPanel.vue'
import PlayerAvatar from '../../components/players/PlayerAvatar.vue'
import StatCard from '../../components/ui/StatCard.vue'
import AppButton from '../../components/ui/AppButton.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import { usePlayersStore } from '../../stores/players'
import { useServerStore } from '../../stores/server'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

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

// ── Lookup maps (lowercased name → entry) ───────────────────────────────────
const onlineMap = computed(() => new Map(store.online.map(p => [p.name.toLowerCase(), p])))
const opMap = computed(() => new Map(store.ops.map(o => [o.name.toLowerCase(), o])))
const bannedMap = computed(() => new Map(store.bans.map(b => [b.name.toLowerCase(), b])))
const whitelistSet = computed(() => new Set(store.whitelist.map(w => (w.name || '').toLowerCase())))

// The backend derives last-seen from each player's playerdata file mtime and
// ships it as an ISO-8601 string (or null). Parse to a Date; a missing or
// unparseable value stays null and renders as "never seen".
function parseLastSeen(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

function relativeTime(date) {
  if (!date || Number.isNaN(date.getTime())) return ''
  const m = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000))
  if (m < 1) return t('players.justNow')
  if (m < 60) return t('players.minutesAgo', { n: m })
  const h = Math.floor(m / 60)
  if (h < 24) return t('players.hoursAgo', { n: h })
  return t('players.daysAgo', { n: Math.floor(h / 24) })
}

// Merge every player we know about — known players plus anyone with a role
// (whitelist/op/ban) who may never have joined — into one list.
const allPlayers = computed(() => {
  const byKey = new Map()
  const ensure = (name, uuid) => {
    const key = (name || '').toLowerCase()
    if (!byKey.has(key)) byKey.set(key, { name, uuid: uuid || null, lastSeen: null })
    else if (uuid && !byKey.get(key).uuid) byKey.get(key).uuid = uuid
    return byKey.get(key)
  }

  for (const p of store.knownPlayers) {
    const row = ensure(p.name, p.uuid)
    row.lastSeen = parseLastSeen(p.lastSeen)
  }
  for (const w of store.whitelist) ensure(w.name, w.uuid)
  for (const o of store.ops) ensure(o.name, o.uuid)
  for (const b of store.bans) ensure(b.name, b.uuid)
  for (const o of store.online) ensure(o.name, o.uuid)

  const rows = [...byKey.values()].map(row => {
    const key = row.name.toLowerCase()
    const op = opMap.value.get(key)
    return {
      name: row.name,
      uuid: row.uuid,
      isOnline: onlineMap.value.has(key),
      lastSeen: row.lastSeen,
      isOp: !!op,
      opLevel: op?.level ?? 4,
      isBanned: bannedMap.value.has(key),
      isWhitelisted: whitelistSet.value.has(key),
    }
  })
  return rows.sort((a, b) => {
    if (a.isOnline !== b.isOnline) return a.isOnline ? -1 : 1
    return (b.lastSeen?.getTime() ?? 0) - (a.lastSeen?.getTime() ?? 0)
  })
})

// ── Filtering / search ──────────────────────────────────────────────────────
const filter = ref('all')
const search = ref('')

const filters = computed(() => [
  { id: 'all', label: t('players.filters.all'), count: allPlayers.value.length },
  { id: 'online', label: t('players.filters.online'), count: store.online.length },
  { id: 'whitelisted', label: t('players.filters.whitelisted'), count: store.whitelist.length },
  { id: 'ops', label: t('players.filters.ops'), count: store.ops.length },
  { id: 'banned', label: t('players.filters.banned'), count: store.bans.length },
])

const filteredPlayers = computed(() => {
  let list = allPlayers.value
  if (filter.value === 'online') list = list.filter(p => p.isOnline)
  else if (filter.value === 'whitelisted') list = list.filter(p => p.isWhitelisted)
  else if (filter.value === 'ops') list = list.filter(p => p.isOp)
  else if (filter.value === 'banned') list = list.filter(p => p.isBanned)
  const q = search.value.trim().toLowerCase()
  return q ? list.filter(p => p.name.toLowerCase().includes(q)) : list
})

// Only show the full-page loading state on the initial load (no data yet) —
// loadAll() drives store.loading, while the 5s online poll does not.
const showLoading = computed(() => store.loading && !allPlayers.value.length)

const emptyMessage = computed(() => {
  if (search.value.trim()) return t('players.empty.search', { query: search.value.trim() })
  switch (filter.value) {
    case 'online': return store.isRunning ? t('players.empty.online') : t('players.empty.onlineStopped')
    case 'whitelisted': return t('players.empty.whitelisted')
    case 'ops': return t('players.empty.ops')
    case 'banned': return t('players.empty.banned')
    default: return t('players.empty.all')
  }
})

async function retry() {
  await store.loadAll()
  if (store.isRunning) store.startOnlinePolling()
}

async function safe(fn) {
  try { await fn() } catch (e) { toast.error(e.message || t('common.operationFailed')) }
}

// Perform a reversible removal, then offer an Undo toast that restores it.
async function removeWithUndo(message, removeFn, undoFn) {
  try {
    await removeFn()
  } catch (e) {
    toast.error(e.message || t('common.operationFailed'))
    return
  }
  toast.action(message, t('common.undo'), () => safe(undoFn))
}

// ── Inline reason entry (shared by kick + ban) ──────────────────────────────
const reasonTarget = ref(null)  // { name, mode: 'kick' | 'ban' }
const reasonText = ref('')
const reasonInputEl = ref(null)  // only one reason input is rendered at a time

async function startReason(name, mode) {
  reasonTarget.value = { name, mode }
  reasonText.value = ''
  await nextTick()
  // The ref lives inside the players v-for, so Vue collects it into an ARRAY —
  // calling .focus() on the array threw and the input never focused. Only one
  // reason input is rendered at a time (v-if on the matching row), so focus its
  // single entry.
  const el = reasonInputEl.value
  const input = Array.isArray(el) ? el[0] : el
  input?.focus()
}

function cancelReason() {
  reasonTarget.value = null
  reasonText.value = ''
}

async function submitReason() {
  const target = reasonTarget.value
  if (!target) return
  const reason = reasonText.value.trim() || null
  if (target.mode === 'kick') await safe(() => store.kick(target.name, reason))
  else await safe(() => store.addBan(target.name, reason))
  cancelReason()
}

// ── Role toggles ────────────────────────────────────────────────────────────
function toggleWhitelist(p) {
  if (p.isWhitelisted) {
    removeWithUndo(
      t('players.removedFromWhitelist', { name: p.name }),
      () => store.removeWhitelist(p.name),
      () => store.addWhitelist(p.name)
    )
  } else safe(() => store.addWhitelist(p.name))
}

function toggleOp(p) {
  if (p.isOp) {
    const level = p.opLevel  // capture so Undo restores the same level
    removeWithUndo(
      t('players.removedOperator', { name: p.name }),
      () => store.removeOp(p.name),
      () => store.addOp(p.name, level)
    )
  } else safe(() => store.addOp(p.name, 4))  // vanilla defaults to 4; level editable below when stopped
}

function unban(p) {
  const reason = bannedMap.value.get(p.name.toLowerCase())?.reason ?? null  // restore same reason on Undo
  removeWithUndo(
    t('players.unbanned', { name: p.name }),
    () => store.removeBan(p.name),
    () => store.addBan(p.name, reason)
  )
}

function changeOpLevel(p, level) {
  if (store.isRunning) return  // disabled in template; defensive guard
  safe(() => store.setOpLevel(p.name, Number(level)))
}

// ── Add a player who hasn't joined yet ──────────────────────────────────────
const addName = ref('')
const addBusy = ref(false)

async function addPlayer(action) {
  const name = addName.value.trim()
  if (!name || addBusy.value) return
  addBusy.value = true
  try {
    if (action === 'whitelist') await store.addWhitelist(name)
    else if (action === 'op') await store.addOp(name, 4)
    else if (action === 'ban') await store.addBan(name, null)
    addName.value = ''
  } catch (e) {
    toast.error(e.message || t('common.operationFailed'))
  } finally {
    addBusy.value = false
  }
}

// ── Whitelist enforcement settings ──────────────────────────────────────────
function onToggleActive(value) {
  safe(() => store.toggleWhitelistActive(value))
}
function onToggleEnforce(value) {
  safe(() => store.toggleEnforceWhitelist(value))
}
</script>

<template>
  <div class="players-page">
    <div v-if="!store.onlineMode" class="players-page__offline-banner" role="status">
      {{ $t('players.offlineMode') }}
    </div>

    <div v-if="store.error" class="players-page__error-banner" role="alert">
      <span>{{ store.error }}</span>
      <AppButton variant="ghost" size="sm" :loading="store.loading" @click="retry">{{ $t('common.retry') }}</AppButton>
    </div>

    <!-- Stats -->
    <div class="players-stats">
      <StatCard :label="$t('players.stats.online')" :value="store.online.length" accent="success" />
      <StatCard :label="$t('players.stats.whitelisted')" :value="store.whitelist.length" />
      <StatCard :label="$t('players.stats.ops')" :value="store.ops.length" accent="primary" />
      <StatCard :label="$t('players.stats.banned')" :value="store.bans.length" accent="danger" />
    </div>

    <!-- Whitelist enforcement -->
    <section class="whitelist-settings">
      <ToggleRow
        v-if="store.isRunning"
        :label="$t('players.whitelistRuntime')"
        :model-value="store.whitelistActive"
        @update:model-value="onToggleActive"
      />
      <ToggleRow
        v-else
        :label="$t('players.enforceWhitelist')"
        :model-value="store.enforceWhitelist"
        @update:model-value="onToggleEnforce"
      />
      <p class="whitelist-settings__hint">
        <template v-if="store.isRunning">{{ $t('players.whitelistRuntimeHint') }}</template>
        <template v-else>{{ $t('players.enforceWhitelistHint') }}</template>
      </p>
    </section>

    <!-- Toolbar: filters + search -->
    <div class="players-toolbar">
      <div class="players-filters">
        <button
          v-for="f in filters"
          :key="f.id"
          :class="['filter-pill', { 'filter-pill--active': filter === f.id }]"
          type="button"
          @click="filter = f.id"
        >{{ f.label }} <span class="filter-pill__count">{{ f.count }}</span></button>
      </div>
      <input v-model="search" class="players-search" type="search" :placeholder="$t('players.search')" />
    </div>

    <!-- Add a player who hasn't joined -->
    <form class="player-add" @submit.prevent="addPlayer('whitelist')">
      <input
        v-model="addName"
        class="player-add__input"
        type="text"
        :placeholder="$t('players.addPlaceholder')"
        :disabled="addBusy"
      />
      <AppButton type="submit" variant="primary" size="sm" :loading="addBusy" :disabled="!addName.trim()">{{ $t('players.addWhitelist') }}</AppButton>
      <AppButton type="button" variant="ghost" size="sm" :disabled="!addName.trim() || addBusy" @click="addPlayer('op')">{{ $t('players.addOp') }}</AppButton>
      <AppButton type="button" variant="danger" size="sm" :disabled="!addName.trim() || addBusy" @click="addPlayer('ban')">{{ $t('players.ban') }}</AppButton>
    </form>

    <!-- Loading state (initial load only) -->
    <div v-if="showLoading" class="player-list__loading">
      <span class="player-list__spinner" aria-hidden="true" />
      {{ $t('players.loading') }}
    </div>

    <!-- Unified player list -->
    <ul v-else class="player-list">
      <li v-for="p in filteredPlayers" :key="p.uuid || p.name" class="player-row">
        <span :class="['status-dot', p.isOnline ? 'status-dot--online' : 'status-dot--offline']" />
        <PlayerAvatar :name="p.name" :uuid="p.uuid" :offline-mode="!store.onlineMode" :size="28" />

        <div class="player-row__main">
          <span class="player-row__name">{{ p.name }}</span>
          <span class="player-row__when">{{ p.isOnline ? $t('players.online') : (relativeTime(p.lastSeen) || $t('players.neverSeen')) }}</span>
        </div>

        <!-- Reason entry mode replaces the actions -->
        <template v-if="reasonTarget && reasonTarget.name === p.name">
          <input
            ref="reasonInputEl"
            v-model="reasonText"
            class="reason-input"
            type="text"
            :placeholder="reasonTarget.mode === 'kick' ? $t('players.kickReason') : $t('players.banReason')"
            maxlength="256"
            @keydown.enter.prevent="submitReason"
            @keydown.escape="cancelReason"
          />
          <AppButton variant="danger" size="sm" @click="submitReason">
            {{ reasonTarget.mode === 'kick' ? $t('players.kick') : $t('players.ban') }}
          </AppButton>
          <AppButton variant="ghost" size="sm" @click="cancelReason">✕</AppButton>
        </template>

        <!-- Default: role chips + actions -->
        <div v-else class="player-row__roles">
          <button
            :class="['role-chip', { 'role-chip--on': p.isWhitelisted }]"
            type="button"
            :title="p.isWhitelisted ? $t('players.removeFromWhitelist') : $t('players.addToWhitelist')"
            @click="toggleWhitelist(p)"
          >{{ p.isWhitelisted ? $t('players.whitelisted') : $t('players.addWhitelist') }}</button>

          <span v-if="p.isOp" class="op-control">
            <button class="role-chip role-chip--on role-chip--op" type="button" :title="$t('players.removeOperator')" @click="toggleOp(p)">{{ $t('players.op') }}</button>
            <select
              :value="p.opLevel"
              class="op-level"
              :disabled="store.isRunning"
              :title="store.isRunning ? $t('players.stopToChangeLevel') : $t('players.operatorLevel')"
              @change="changeOpLevel(p, $event.target.value)"
            >
              <option v-for="l in [1,2,3,4]" :key="l" :value="l">{{ $t('players.levelShort', { level: l }) }}</option>
            </select>
          </span>
          <button v-else class="role-chip" type="button" :title="$t('players.makeOperator')" @click="toggleOp(p)">{{ $t('players.addOp') }}</button>

          <span class="player-row__spacer" />

          <AppButton v-if="p.isOnline" variant="ghost" size="sm" @click="startReason(p.name, 'kick')">{{ $t('players.kick') }}</AppButton>
          <AppButton v-if="p.isBanned" variant="ghost" size="sm" @click="unban(p)">{{ $t('players.unban') }}</AppButton>
          <AppButton v-else variant="danger" size="sm" @click="startReason(p.name, 'ban')">{{ $t('players.ban') }}</AppButton>
        </div>
      </li>
      <li v-if="!filteredPlayers.length" class="player-list__empty">{{ emptyMessage }}</li>
    </ul>

    <IpBansPanel />
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

.players-page__error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: var(--text-sm);
}

/* ── Stats ── */
.players-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
}

/* ── Whitelist settings ── */
.whitelist-settings {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}
.whitelist-settings__hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

/* ── Toolbar ── */
.players-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.players-filters {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.filter-pill {
  height: 28px;
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

.filter-pill:hover { color: var(--text-secondary); }

.filter-pill--active {
  background: rgba(249, 115, 22, 0.12);
  border-color: var(--primary);
  color: var(--primary);
}

.filter-pill__count {
  opacity: 0.7;
  font-variant-numeric: tabular-nums;
}

.players-search {
  height: 32px;
  flex: 1;
  min-width: 160px;
  max-width: 240px;
  margin-left: auto;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
}
.players-search:focus { outline: none; border-color: var(--primary); }

/* ── Add player ── */
.player-add {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.player-add__input {
  flex: 1;
  max-width: 280px;
  height: 32px;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
}
.player-add__input:focus { outline: none; border-color: var(--primary); }

/* ── Player list ── */
.player-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.player-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}
.player-row:last-child { border-bottom: none; }

.player-row__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.player-row__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.player-row__when {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  font-family: var(--font-mono);
}

.player-row__roles {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.player-row__spacer { width: var(--space-1); }

/* ── Status dot ── */
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot--online  { background: var(--success); }
.status-dot--offline { background: var(--text-disabled); }

/* ── Role chips (always-visible toggles) ── */
.role-chip {
  height: 26px;
  padding: 0 var(--space-2);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  white-space: nowrap;
}
.role-chip:hover { color: var(--text-secondary); border-color: var(--text-muted); }

.role-chip--on {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.3);
  color: var(--success);
}
.role-chip--op.role-chip--on {
  background: rgba(249, 115, 22, 0.12);
  border-color: rgba(249, 115, 22, 0.35);
  color: var(--primary);
}

.op-control { display: inline-flex; align-items: center; gap: var(--space-1); }
.op-level {
  height: 26px;
  padding: 0 var(--space-1);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-xs);
}
.op-level:disabled { opacity: 0.5; cursor: not-allowed; }

.player-list__empty {
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--text-disabled);
}

.player-list__loading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.player-list__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: players-spin 0.7s linear infinite;
}

@keyframes players-spin {
  to { transform: rotate(360deg); }
}

/* ── Inline reason input ── */
.reason-input {
  height: 26px;
  width: 160px;
  flex-shrink: 0;
  padding: 0 var(--space-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-xs);
}
.reason-input:focus { outline: none; border-color: var(--danger); }
/* Mobile: the toolbar already wraps, so the work here is letting the search
   and add-player inputs use the width the wrap gives them instead of holding
   their desktop max-widths, and halving the stat grid. */
@media (max-width: 768px) {
  .players-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .players-search,
  .player-add__input {
    flex: 1;
    min-width: 0;
    max-width: none;
  }

  .player-add {
    width: 100%;
  }

  /* The row is name + roles + actions; below this width they stack rather than
     squeeze the name to a few characters. */
  .player-row {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }

  .player-row__main {
    flex-basis: 100%;
  }

  .player-row__spacer {
    display: none;
  }

  .reason-input {
    width: 100%;
  }
}
</style>
