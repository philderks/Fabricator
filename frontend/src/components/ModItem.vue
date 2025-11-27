<script setup>
defineProps({
  mod: {
    type: Object,
    required: true
  }
})

defineEmits(['update', 'remove'])
</script>

<template>
  <div class="mod-item">
    <div class="mod-main">
      <div class="mod-name">{{ mod.name }}</div>
      <div class="mod-meta">
        <span class="mod-version">v{{ mod.version }}</span>
        <span class="mod-separator">•</span>
        <span class="mod-category">{{ mod.category }}</span>
        <span class="mod-separator">•</span>
        <span class="mod-downloads">{{ mod.downloads }} downloads</span>
      </div>
    </div>
    <div class="mod-actions">
      <button class="btn-text" @click="$emit('update', mod)">Update</button>
      <button class="btn-text danger" @click="$emit('remove', mod)">Remove</button>
    </div>
  </div>
</template>

<style scoped>
.mod-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  transition: all 0.2s;
}

.mod-item:hover {
  border-color: var(--border-hover);
}

.mod-main {
  flex: 1;
}

.mod-name {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.375rem;
}

.mod-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-disabled);
}

.mod-version {
  color: var(--text-muted);
}

.mod-category {
  padding: 0.125rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 0.75rem;
}

.mod-separator {
  color: #475569;
}

.mod-actions {
  display: flex;
  gap: 0.5rem;
}

@media (max-width: 768px) {
  .mod-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .mod-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
