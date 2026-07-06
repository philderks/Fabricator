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
    const optimistic = { name, uuid: null }
    whitelist.value = [...whitelist.value, optimistic]
    try {
      const result = await api.addToWhitelist(id, name)
      whitelist.value = whitelist.value.map(e =>
        e === optimistic ? { name: result.name, uuid: result.uuid || null } : e
      )
    } catch (e) {
      whitelist.value = whitelist.value.filter(e => e !== optimistic)
      throw e
    }
  }

  async function removeWhitelist(name) {
    const id = currentServerId.value
    const before = whitelist.value
    whitelist.value = whitelist.value.filter(
      e => (e.name || '').toLowerCase() !== name.toLowerCase()
    )
    try {
      await api.removeFromWhitelist(id, name)
    } catch (e) {
      whitelist.value = before
      throw e
    }
  }

  async function toggleWhitelistActive(active) {
    const previous = whitelistActive.value
    whitelistActive.value = active
    try {
      await api.setWhitelistActive(currentServerId.value, active)
    } catch (e) {
      whitelistActive.value = previous
      throw e
    }
  }

  async function addOp(name, level) {
    const id = currentServerId.value
    const optimistic = { name, level, uuid: null }
    ops.value = [...ops.value, optimistic]
    try {
      const result = await api.addOp(id, name, level)
      ops.value = ops.value.map(e =>
        e === optimistic
          ? { name: result.name, uuid: result.uuid || null, level: result.level ?? level }
          : e
      )
    } catch (e) {
      ops.value = ops.value.filter(e => e !== optimistic)
      throw e
    }
  }

  async function setOpLevel(name, level) {
    const before = ops.value
    ops.value = ops.value.map(e =>
      (e.name || '').toLowerCase() === name.toLowerCase() ? { ...e, level } : e
    )
    try {
      await api.setOpLevel(currentServerId.value, name, level)
    } catch (e) {
      ops.value = before
      throw e
    }
  }

  async function removeOp(name) {
    const before = ops.value
    ops.value = ops.value.filter(
      e => (e.name || '').toLowerCase() !== name.toLowerCase()
    )
    try {
      await api.removeOp(currentServerId.value, name)
    } catch (e) {
      ops.value = before
      throw e
    }
  }

  async function addBan(name, reason) {
    const id = currentServerId.value
    const optimistic = { name, reason, uuid: null }
    bans.value = [...bans.value, optimistic]
    try {
      const result = await api.banPlayer(id, name, reason || null)
      bans.value = bans.value.map(e =>
        e === optimistic
          ? { name: result.name, uuid: result.uuid || null, reason: result.reason }
          : e
      )
    } catch (e) {
      bans.value = bans.value.filter(e => e !== optimistic)
      throw e
    }
  }

  async function removeBan(name) {
    const before = bans.value
    bans.value = bans.value.filter(
      e => (e.name || '').toLowerCase() !== name.toLowerCase()
    )
    try {
      await api.unbanPlayer(currentServerId.value, name)
    } catch (e) {
      bans.value = before
      throw e
    }
  }

  async function kick(name, reason = null) {
    await api.kickPlayer(currentServerId.value, name, reason)
    // No optimistic update — Minecraft will emit a leave line that updates
    // _players naturally, and the next /online poll reflects it.
  }

  async function addIpBan(ip, reason = null) {
    const id = currentServerId.value
    const optimistic = { ip, reason }
    ipBans.value = [...ipBans.value, optimistic]
    try {
      const result = await api.banIp(id, ip, reason || null)
      ipBans.value = ipBans.value.map(e => e === optimistic ? result : e)
    } catch (e) {
      ipBans.value = ipBans.value.filter(e => e !== optimistic)
      throw e
    }
  }

  async function removeIpBan(ip) {
    const before = ipBans.value
    ipBans.value = ipBans.value.filter(
      e => (e.ip || '').toLowerCase() !== ip.toLowerCase()
    )
    try {
      await api.unbanIp(currentServerId.value, ip)
    } catch (e) {
      ipBans.value = before
      throw e
    }
  }

  async function toggleEnforceWhitelist(active) {
    const previous = enforceWhitelist.value
    enforceWhitelist.value = active
    try {
      await api.setEnforceWhitelist(currentServerId.value, active)
    } catch (e) {
      enforceWhitelist.value = previous
      throw e
    }
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
