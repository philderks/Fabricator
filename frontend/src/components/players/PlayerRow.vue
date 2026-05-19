<script setup>
import PlayerAvatar from './PlayerAvatar.vue'

defineProps({
  name: { type: String, required: true },
  uuid: { type: String, default: null },
  offlineMode: { type: Boolean, default: false },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <li class="player-row">
    <PlayerAvatar :name="name" :uuid="uuid" :offline-mode="offlineMode" :size="28" />
    <div class="player-row__main">
      <span class="player-row__name">{{ name }}</span>
      <span v-if="subtitle" class="player-row__subtitle">{{ subtitle }}</span>
    </div>
    <div class="player-row__actions">
      <slot name="actions" />
    </div>
  </li>
</template>

<style scoped>
.player-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}
.player-row:last-child {
  border-bottom: none;
}
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
.player-row__subtitle {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  font-family: var(--font-mono);
}
.player-row__actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-shrink: 0;
}
</style>
