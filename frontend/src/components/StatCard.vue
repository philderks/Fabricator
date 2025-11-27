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
  highlight: {
    type: Boolean,
    default: false
  }
})
</script>

<template>
  <div class="stat-card">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-value" :class="{ highlight }">{{ value }}</div>
  </div>
</template>

<style scoped>
.stat-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 1.5rem;
}

.stat-label {
  color: #94a3b8;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #f1f5f9;
}

.stat-value.highlight {
  color: #10b981;
}
</style>
