<script setup>
defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (v) => ['primary', 'ghost', 'danger', 'warning'].includes(v)
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md'].includes(v)
  },
  loading: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  type: {
    type: String,
    default: 'button',
    validator: (v) => ['button', 'submit', 'reset'].includes(v)
  }
})

defineEmits(['click'])
</script>

<template>
  <button
    :type="type"
    class="app-btn"
    :class="[`app-btn--${variant}`, `app-btn--${size}`, { 'is-loading': loading }]"
    :disabled="disabled || loading"
    :aria-busy="loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="app-btn__spinner" aria-hidden="true"></span>
    <span class="app-btn__label"><slot /></span>
  </button>
</template>

<style scoped>
.app-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  white-space: nowrap;
}

.app-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.app-btn--sm {
  padding: 4px 10px;
  font-size: var(--text-xs);
  height: 26px;
}

.app-btn--md {
  padding: 6px 14px;
  font-size: var(--text-sm);
  height: 32px;
}

.app-btn--primary {
  background: var(--primary);
  color: var(--text-on-primary);
}

.app-btn--primary:hover:not(:disabled) {
  background: var(--primary-dark);
}

.app-btn--ghost {
  background: var(--bg-tertiary);
  color: var(--text-muted);
  border-color: var(--border-color);
}

.app-btn--ghost:hover:not(:disabled) {
  background: var(--secondary-hover);
  color: var(--text-secondary);
}

.app-btn--danger {
  background: var(--danger);
  color: var(--text-on-primary);
}

.app-btn--danger:hover:not(:disabled) {
  background: var(--danger-dark);
}

.app-btn--warning {
  background: var(--warning);
  color: var(--bg-primary);
}

.app-btn--warning:hover:not(:disabled) {
  background: var(--warning-dark);
}

.app-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.app-btn.is-loading .app-btn__label {
  opacity: 0.7;
}

.app-btn__spinner {
  width: 12px;
  height: 12px;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: app-btn-spin 0.6s linear infinite;
}

@keyframes app-btn-spin {
  to { transform: rotate(360deg); }
}
</style>
