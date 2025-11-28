<script setup>
const props = defineProps({
  mod: {
    type: Object,
    required: true
  }
})

defineEmits(['update', 'remove'])

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes)) {
    return '—'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[idx]}`
}

const formatUpdated = (timestamp) => {
  if (!timestamp) {
    return ''
  }
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return date.toLocaleDateString()
}

const versionLabel = () => {
  if (!props.mod.version || props.mod.version === 'local') {
    return 'Local'
  }
  return props.mod.version
}
</script>

<template>
  <div class="mod-item">
    <div class="mod-main">
      <div class="mod-name">{{ mod.name }}</div>
      <div class="mod-meta">
        <span class="mod-version">{{ versionLabel() }}</span>
        <span class="mod-separator" v-if="mod.size && mod.size > 0">•</span>
        <span class="mod-size" v-if="mod.size && mod.size > 0">{{ formatBytes(mod.size) }}</span>
        <span class="mod-separator" v-if="mod.updatedAt">•</span>
        <span class="mod-updated" v-if="mod.updatedAt">Updated {{ formatUpdated(mod.updatedAt) }}</span>
        <span class="mod-separator" v-if="mod.source || mod.category">•</span>
        <span class="mod-category" v-if="mod.source || mod.category">{{ mod.source || mod.category }}</span>
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
  text-transform: capitalize;
}

.mod-size,
.mod-updated {
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
