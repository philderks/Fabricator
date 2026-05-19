<script setup>
import { computed, ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'

const store = usePlayersStore()

const expanded = ref(false)
const search = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return store.knownPlayers
  return store.knownPlayers.filter(p => (p.name || '').toLowerCase().includes(q))
})

const title = computed(() => `Known players (${store.knownPlayers.length})`)

async function safe(fn) {
  try { await fn() } catch (e) { console.error(e) }
}
</script>

<template>
  <Panel :title="title">
    <template #action>
      <button class="known-toggle" type="button" @click="expanded = !expanded">
        {{ expanded ? 'Collapse' : 'Expand' }}
      </button>
    </template>

    <div v-if="expanded">
      <input v-model="search" class="known-search" type="search" placeholder="Search known players…" />
      <ul v-if="filtered.length" class="known-list">
        <PlayerRow
          v-for="p in filtered"
          :key="p.uuid || p.name"
          :name="p.name"
          :uuid="p.uuid"
          :offline-mode="!store.onlineMode"
          :subtitle="p.expiresOn ? `last seen ${String(p.expiresOn).split(' ')[0]}` : ''"
        >
          <template #actions>
            <AppButton variant="ghost" size="sm" @click="safe(() => store.addWhitelist(p.name))">+ Whitelist</AppButton>
            <AppButton variant="ghost" size="sm" @click="safe(() => store.addOp(p.name, 4))">+ Op</AppButton>
            <AppButton variant="danger" size="sm" @click="safe(() => store.addBan(p.name, null))">Ban</AppButton>
          </template>
        </PlayerRow>
      </ul>
      <div v-else class="known-empty">
        <template v-if="search">No matches.</template>
        <template v-else>No known players yet.</template>
      </div>
    </div>
  </Panel>
</template>

<style scoped>
.known-toggle {
  background: none; border: none;
  font-size: var(--text-xs); color: var(--primary);
  cursor: pointer; padding: 0;
}
.known-toggle:hover { text-decoration: underline; }
.known-search {
  width: 100%; height: 32px; padding: 0 var(--space-3);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); color: var(--text-primary);
  font-size: var(--text-sm); margin-bottom: var(--space-2);
}
.known-list { list-style: none; margin: 0; padding: 0; }
.known-empty { padding: var(--space-3) 0; font-size: var(--text-sm); color: var(--text-disabled); }
</style>
