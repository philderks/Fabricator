<script setup>
import AppButton from '../ui/AppButton.vue'

defineEmits(['add-server'])
</script>

<template>
  <header class="root-topbar">
    <div class="root-topbar__brand">
      <img src="/favicon.svg" alt="" class="root-topbar__logo" aria-hidden="true" />
      <span class="root-topbar__name">Fabricator</span>
    </div>
    <div class="root-topbar__actions">
      <AppButton variant="primary" size="md" @click="$emit('add-server')">
        + Add server
      </AppButton>
    </div>
  </header>
</template>

<style scoped>
.root-topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.root-topbar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.root-topbar__logo {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
}

.root-topbar__name {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}

.root-topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
