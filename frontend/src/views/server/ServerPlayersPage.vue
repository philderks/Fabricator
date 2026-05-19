<script setup>
import { onMounted, onUnmounted, watch } from 'vue'
import OnlinePlayersPanel from '../../components/players/OnlinePlayersPanel.vue'
import WhitelistPanel from '../../components/players/WhitelistPanel.vue'
import OpsPanel from '../../components/players/OpsPanel.vue'
import BansPanel from '../../components/players/BansPanel.vue'
import KnownPlayersPanel from '../../components/players/KnownPlayersPanel.vue'
import { usePlayersStore } from '../../stores/players'
import { useServerStore } from '../../stores/server'

const store = usePlayersStore()
const serverStore = useServerStore()

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
</script>

<template>
  <div class="players-page">
    <div v-if="!store.onlineMode" class="players-page__offline-banner" role="status">
      Server is in offline mode — player avatars and online identity verification are unavailable.
    </div>

    <OnlinePlayersPanel v-if="store.isRunning" />
    <WhitelistPanel />
    <OpsPanel />
    <BansPanel />
    <KnownPlayersPanel />
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
</style>
