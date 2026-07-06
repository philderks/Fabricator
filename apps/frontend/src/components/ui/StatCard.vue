<script setup>
defineProps({
  label: {
    type: String,
    required: true
  },
  value: {
    type: [String, Number],
    required: true
  },
  unit: {
    type: String,
    default: ''
  },
  accent: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'success', 'primary', 'warning', 'danger'].includes(v)
  }
})
</script>

<template>
  <div class="stat-card">
    <div class="stat-card__label">{{ label }}</div>
    <div class="stat-card__value" :class="`stat-card__value--${accent}`">
      <span>{{ value }}</span>
      <span v-if="unit" class="stat-card__unit">{{ unit }}</span>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.stat-card__label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-disabled);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.stat-card__value {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  display: flex;
  align-items: baseline;
  gap: var(--space-1);
}

.stat-card__value--success { color: var(--success); }
.stat-card__value--primary { color: var(--primary); }
.stat-card__value--warning { color: var(--warning); }
.stat-card__value--danger  { color: var(--danger); }

.stat-card__unit {
  font-size: var(--text-sm);
  color: var(--text-disabled);
  font-weight: 400;
}
</style>
