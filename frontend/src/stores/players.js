/**
 * Player Management Store (setup syntax, parallels stores/backups.js).
 *
 * Owns:
 *   - whitelist / ops / bans / known-players lists
 *   - whitelistActive / enforceWhitelist / onlineMode flags
 *   - the live "online players" list with a 5s polling interval
 *
 * Writes use optimistic mutations: an inserted/removed entry is applied
 * immediately, then reconciled against the server's response (replacing
 * placeholder UUIDs) or rolled back on failure.
 *
 * Online polling is best-effort and guarded by the parent server store —
 * it only runs while the server reports `running`, and it self-stops if
 * the active server id changes during the interval.
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useServerStore } from './server'
import * as api from '../api/players'

const ONLINE_POLL_MS = 5000

/**
 * Write `mutate()` to `target` now; restore it and re-throw if `call()` fails.
 *
 * Resolves to `undefined`, never to the response: these actions report through
 * the store's own state, and handing the raw payload back would invite a caller
 * to read it from here instead.
 */
async function optimistic(target, mutate, call) {
  const before = target.value
  mutate()
  try {
    await call()
  } catch (e) {
    target.value = before
    throw e
  }
}

/**
 * Append `entry` now, then swap it for what the server recorded — the
 * placeholder carries no UUID until the server resolves one. A failure removes
 * just that entry, so a concurrent change isn't discarded with it.
 */
async function optimisticAdd(list, entry, call, reconcile) {
  list.value = [...list.value, entry]
  try {
    const result = await call()
    list.value = list.value.map(e => (e === entry ? reconcile(result) : e))
  } catch (e) {
    list.value = list.value.filter(x => x !== entry)
    throw e
  }
}

/** Case-insensitive "every entry but this one" filter on a name-ish field. */
const excluding = (field, value) => (e) =>
  (e[field] || '').toLowerCase() !== String(value).toLowerCase()

export const usePlayersStore = defineStore('players', () => {
  const serverStore = useServerStore()

  // ---------- State ----------
  const whitelist = ref([])
  const ops = ref([])
  const bans = ref([])
  const ipBans = ref([])
  const knownPlayers = ref([])
  const online = ref([])
  const whitelistActive = ref(false)
  const enforceWhitelist = ref(false)
  const onlineMode = ref(true)
  const loading = ref(false)
  const error = ref(null)

  // Internal-only — not exposed via the return.
  const _onlinePollHandle = ref(null)
  const _onlinePollServerId = ref(null)

  // ---------- Getters ----------
  const currentServerId = computed(() => serverStore.currentServerId)
  const isRunning = computed(() => serverStore.serverStatus?.status === 'running')

  // ---------- Actions ----------

  async function loadAll() {
    const id = currentServerId.value
    if (!id) return
    loading.value = true
    error.value = null
    try {
      const state = await api.getPlayersState(id)
      whitelist.value = state.whitelist || []
      ops.value = state.ops || []
      bans.value = state.bans || []
      ipBans.value = state.ipBans || []
      knownPlayers.value = state.knownPlayers || []
      whitelistActive.value = !!state.whitelistActive
      enforceWhitelist.value = !!state.enforceWhitelist
      onlineMode.value = state.onlineMode !== false
      if (isRunning.value) await loadOnline()
    } catch (e) {
      error.value = e.message || 'Failed to load player state'
    } finally {
      loading.value = false
    }
  }

  async function loadOnline() {
    const id = currentServerId.value
    if (!id || !isRunning.value) {
      online.value = []
      return
    }
    try {
      online.value = await api.getOnlinePlayers(id)
    } catch (e) {
      // Don't surface — online polling is best-effort.
    }
  }

  function startOnlinePolling() {
    stopOnlinePolling()
    if (!isRunning.value) return
    _onlinePollServerId.value = currentServerId.value
    _onlinePollHandle.value = setInterval(() => {
      if (!isRunning.value || currentServerId.value !== _onlinePollServerId.value) {
        stopOnlinePolling()
        return
      }
      loadOnline()
    }, ONLINE_POLL_MS)
  }

  function stopOnlinePolling() {
    if (_onlinePollHandle.value) {
      clearInterval(_onlinePollHandle.value)
      _onlinePollHandle.value = null
      _onlinePollServerId.value = null
    }
  }

  async function addWhitelist(name) {
    const id = currentServerId.value
    return optimisticAdd(
      whitelist,
      { name, uuid: null },
      () => api.addToWhitelist(id, name),
      (r) => ({ name: r.name, uuid: r.uuid || null })
    )
  }

  async function removeWhitelist(name) {
    return optimistic(
      whitelist,
      () => { whitelist.value = whitelist.value.filter(excluding('name', name)) },
      () => api.removeFromWhitelist(currentServerId.value, name)
    )
  }

  async function toggleWhitelistActive(active) {
    return optimistic(
      whitelistActive,
      () => { whitelistActive.value = active },
      () => api.setWhitelistActive(currentServerId.value, active)
    )
  }

  async function addOp(name, level) {
    const id = currentServerId.value
    return optimisticAdd(
      ops,
      { name, level, uuid: null },
      () => api.addOp(id, name, level),
      (r) => ({ name: r.name, uuid: r.uuid || null, level: r.level ?? level })
    )
  }

  async function setOpLevel(name, level) {
    return optimistic(
      ops,
      () => {
        ops.value = ops.value.map(e =>
          (e.name || '').toLowerCase() === name.toLowerCase() ? { ...e, level } : e
        )
      },
      () => api.setOpLevel(currentServerId.value, name, level)
    )
  }

  async function removeOp(name) {
    return optimistic(
      ops,
      () => { ops.value = ops.value.filter(excluding('name', name)) },
      () => api.removeOp(currentServerId.value, name)
    )
  }

  async function addBan(name, reason) {
    const id = currentServerId.value
    return optimisticAdd(
      bans,
      { name, reason, uuid: null },
      () => api.banPlayer(id, name, reason || null),
      (r) => ({ name: r.name, uuid: r.uuid || null, reason: r.reason })
    )
  }

  async function removeBan(name) {
    return optimistic(
      bans,
      () => { bans.value = bans.value.filter(excluding('name', name)) },
      () => api.unbanPlayer(currentServerId.value, name)
    )
  }

  async function kick(name, reason = null) {
    await api.kickPlayer(currentServerId.value, name, reason)
    // No optimistic update — Minecraft will emit a leave line that updates
    // _players naturally, and the next /online poll reflects it.
  }

  async function addIpBan(ip, reason = null) {
    const id = currentServerId.value
    return optimisticAdd(
      ipBans,
      { ip, reason },
      () => api.banIp(id, ip, reason || null),
      (r) => r
    )
  }

  async function removeIpBan(ip) {
    return optimistic(
      ipBans,
      () => { ipBans.value = ipBans.value.filter(excluding('ip', ip)) },
      () => api.unbanIp(currentServerId.value, ip)
    )
  }

  async function toggleEnforceWhitelist(active) {
    return optimistic(
      enforceWhitelist,
      () => { enforceWhitelist.value = active },
      () => api.setEnforceWhitelist(currentServerId.value, active)
    )
  }

  function resetState() {
    whitelist.value = []
    ops.value = []
    bans.value = []
    ipBans.value = []
    knownPlayers.value = []
    online.value = []
    whitelistActive.value = false
    enforceWhitelist.value = false
    onlineMode.value = true
    error.value = null
  }

  return {
    // state
    whitelist,
    ops,
    bans,
    ipBans,
    knownPlayers,
    online,
    whitelistActive,
    enforceWhitelist,
    onlineMode,
    loading,
    error,
    // getters
    currentServerId,
    isRunning,
    // actions
    loadAll,
    loadOnline,
    startOnlinePolling,
    stopOnlinePolling,
    addWhitelist,
    removeWhitelist,
    toggleWhitelistActive,
    toggleEnforceWhitelist,
    addOp,
    setOpLevel,
    removeOp,
    addBan,
    removeBan,
    addIpBan,
    removeIpBan,
    kick,
    resetState
  }
})
