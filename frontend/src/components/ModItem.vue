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
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  transition: all 0.2s;
}

.mod-item:hover {
  border-color: #3b82f6;
}

.mod-main {
  flex: 1;
}

.mod-name {
  font-weight: 600;
  color: #f1f5f9;
  margin-bottom: 0.375rem;
}

.mod-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: #64748b;
}

.mod-version {
  color: #94a3b8;
}

.mod-category {
  padding: 0.125rem 0.5rem;
  background: #334155;
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

.btn-text {
  background: transparent;
  border: none;
  color: #3b82f6;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
}

.btn-text:hover {
  color: #2563eb;
}

.btn-text.danger {
  color: #ef4444;
}

.btn-text.danger:hover {
  color: #dc2626;
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
