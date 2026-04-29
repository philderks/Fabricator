<script setup>
import ServerSettingsTab from '../../components/server/ServerSettingsTab.vue'
import AppButton from '../../components/ui/AppButton.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()
</script>

<template>
  <div class="settings-page">
    <ServerSettingsTab
      v-if="store.serverSettings"
      :settings="store.serverSettings"
      :server-version="store.serverStatus.version"
      :server-loader="store.serverStatus.loader"
      :can-edit="store.canEditSettings"
      @save="store.handleSaveSettings"
      @reset="store.resetSettings"
    />

    <div class="settings-page__danger-zone">
      <h3 class="settings-page__danger-title">Danger zone</h3>
      <p class="settings-page__danger-text">Deleting a server removes its files and backups. This cannot be undone.</p>
      <AppButton variant="danger" :loading="store.deletingServer" @click="store.openDeleteServerModal">
        {{ store.deletingServer ? 'Deleting…' : 'Delete server' }}
      </AppButton>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.settings-page__danger-zone {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
  background: var(--bg-secondary);
}

.settings-page__danger-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--danger);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.settings-page__danger-text {
  margin: 0 0 var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}
</style>
