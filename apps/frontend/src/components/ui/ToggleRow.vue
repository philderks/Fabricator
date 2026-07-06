<script setup>
import { useId } from 'vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    required: true
  },
  label: {
    type: String,
    required: true
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

defineEmits(['update:modelValue'])

const inputId = useId()
</script>

<template>
  <div class="toggle-row" :class="{ 'toggle-row--disabled': disabled }">
    <div class="toggle-row__text">
      <label :for="inputId" class="toggle-row__label">{{ label }}</label>
    </div>
    <label class="toggle-row__switch" :for="inputId">
      <input
        :id="inputId"
        type="checkbox"
        role="switch"
        :checked="modelValue"
        :disabled="disabled"
        @change="$emit('update:modelValue', $event.target.checked)"
      />
      <span class="toggle-row__track" aria-hidden="true">
        <span class="toggle-row__thumb"></span>
      </span>
    </label>
  </div>
</template>

<style scoped>
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) 0;
}

.toggle-row__text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.toggle-row__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  line-height: var(--leading-tight);
  cursor: pointer;
}

.toggle-row--disabled .toggle-row__label {
  color: var(--text-muted);
  cursor: not-allowed;
}

.toggle-row__switch {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  cursor: pointer;
}

.toggle-row--disabled .toggle-row__switch {
  cursor: not-allowed;
}

.toggle-row__switch input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.toggle-row__track {
  display: inline-block;
  width: 40px;
  height: 22px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  position: relative;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.toggle-row__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--text-muted);
  border-radius: 50%;
  transition: transform 160ms ease, background-color 160ms ease;
}

.toggle-row__switch input:checked + .toggle-row__track {
  background: var(--primary);
  border-color: var(--primary);
}

.toggle-row__switch input:checked + .toggle-row__track .toggle-row__thumb {
  transform: translateX(18px);
  background: var(--text-primary);
}

.toggle-row__switch input:focus-visible + .toggle-row__track {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.toggle-row--disabled .toggle-row__track {
  opacity: 0.5;
}
</style>
