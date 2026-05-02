<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    required: true,
    validator: (v) => ['running', 'stopped', 'pending', 'installing', 'failed', 'unknown'].includes(v)
  },
  label: {
    type: String,
    default: ''
  },
  sub: {
    type: String,
    default: ''
  }
})

const STATUS_META = {
  running:    { dot: 'var(--success)', label: 'Running' },
  stopped:    { dot: 'var(--text-disabled)', label: 'Stopped' },
  pending:    { dot: 'var(--warning)', label: 'Install Required' },
  installing: { dot: 'var(--primary)', label: 'Installing' },
  failed:     { dot: 'var(--danger)', label: 'Failed' },
  unknown:    { dot: 'var(--text-disabled)', label: 'Unknown' }
}

const meta = computed(() => STATUS_META[props.status] || STATUS_META.unknown)
const displayLabel = computed(() => props.label || meta.value.label)
</script>

<template>
  <div class="status-pill" :class="`status-pill--${status}`">
    <span class="status-pill__dot" :style="{ background: meta.dot }"></span>
    <span class="status-pill__label">{{ displayLabel }}</span>
    <span v-if="sub" class="status-pill__sub">· {{ sub }}</span>
  </div>
</template>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  font-size: var(--text-xs);
}

.status-pill__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-pill__label {
  color: var(--text-muted);
  font-weight: 500;
}

.status-pill__sub {
  color: var(--text-disabled);
}

.status-pill--running .status-pill__label {
  color: var(--success);
}
</style>
