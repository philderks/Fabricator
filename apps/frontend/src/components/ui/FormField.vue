<script setup>
import { useId } from 'vue'

defineProps({
  label: {
    type: String,
    required: true
  },
  hint: {
    type: String,
    default: ''
  }
})

const id = useId()
const hintId = useId()

const describedBy = hint => (hint ? hintId : undefined)
</script>

<template>
  <div class="form-field">
    <label :for="id" class="form-field__label">{{ label }}</label>
    <slot :id="id" :describedBy="describedBy(hint)" />
    <p v-if="hint" :id="hintId" class="form-field__hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.form-field__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

.form-field__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin: 0;
  line-height: var(--leading-normal);
}
</style>
