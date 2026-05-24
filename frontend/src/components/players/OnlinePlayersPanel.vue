<script setup>
import { computed, ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'
import { useToast } from '../../composables/useToast'

const store = usePlayersStore()
const toast = useToast()

const title = computed(() => `Online — ${store.online.length}`)

const isOpped = (name) =>
  store.ops.some(o => (o.name || '').toLowerCase() === name.toLowerCase())
const isWhitelisted = (name) =>
  store.whitelist.some(w => (w.name || '').toLowerCase() === name.toLowerCase())

const joinedAgo = (iso) => {
  if (!iso) return ''
  const ms = Date.now() - new Date(iso).getTime()
  const m = Math.max(0, Math.floor(ms / 60000))
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

async function safe(fn) {
  try { await fn() } catch (e) { toast.error(e.message || 'Operation failed') }
}

// ── Kick with reason ───────────────────────────────────────────────────────
const kickTarget = ref(null)
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
  <Panel :title="title">
    <ul v-if="store.online.length" class="online-list">
      <PlayerRow
        v-for="p in store.online"
        :key="p.name"
        :name="p.name"
        :uuid="p.uuid"
        :offline-mode="!store.onlineMode"
        :subtitle="`joined ${joinedAgo(p.joinedAt)}`"
      >
        <template #actions>
          <template v-if="kickTarget === p.name">
            <input
              v-model="kickReason"
              class="online-kick-input"
              type="text"
              placeholder="Kick reason…"
              maxlength="256"
              @keydown.enter.prevent="executeKick(p.name)"
              @keydown.escape="kickTarget = null"
            />
            <AppButton variant="danger" size="sm" @click="executeKick(p.name)">Kick</AppButton>
            <AppButton variant="ghost" size="sm" @click="kickTarget = null">✕</AppButton>
          </template>
          <AppButton v-else variant="ghost" size="sm" @click="startKick(p.name)">Kick</AppButton>
          <AppButton
            v-if="!isOpped(p.name)"
            variant="ghost"
            size="sm"
            @click="safe(() => store.addOp(p.name, 4))"
          >Op</AppButton>
          <AppButton
            v-if="!isWhitelisted(p.name)"
            variant="ghost"
            size="sm"
            @click="safe(() => store.addWhitelist(p.name))"
          >+ Whitelist</AppButton>
          <AppButton variant="danger" size="sm" @click="safe(() => store.addBan(p.name, null))">Ban</AppButton>
        </template>
      </PlayerRow>
    </ul>
    <div v-else class="online-empty">No players online.</div>
  </Panel>
</template>

<style scoped>
.online-list { list-style: none; margin: 0; padding: 0; }
.online-empty {
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--text-disabled);
}
.online-kick-input {
  height: 26px;
  width: 130px;
  padding: 0 var(--space-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-xs);
}
.online-kick-input:focus { outline: none; border-color: var(--danger); }
</style>
