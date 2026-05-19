<script setup>
import { computed } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'

const store = usePlayersStore()

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
  try { await fn() } catch (e) { console.error(e) }
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
          <AppButton variant="ghost" size="sm" @click="safe(() => store.kick(p.name))">Kick</AppButton>
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
</style>
