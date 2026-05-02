<script setup>
import { useId, computed } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true
  },
  hint: {
    type: String,
    default: ''
  },
  error: {
    type: String,
    default: ''
  },
  required: {
    type: Boolean,
    default: false
  }
})

const id = useId()
const hintId = useId()
const errorId = useId()

const describedBy = computed(() => {
  const ids = []
  if (props.hint) ids.push(hintId)
  if (props.error) ids.push(errorId)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div class="form-field" :class="{ 'form-field--error': error }">
    <label :for="id" class="form-field__label">
      {{ label }}
      <span v-if="required" class="form-field__required" aria-hidden="true">*</span>
    </label>
    <slot :id="id" :describedBy="describedBy" />
    <p v-if="hint && !error" :id="hintId" class="form-field__hint">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="form-field__error" role="alert">{{ error }}</p>
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

.form-field__required {
  color: var(--danger);
  margin-left: var(--space-1);
}

.form-field__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin: 0;
  line-height: var(--leading-normal);
}

.form-field__error {
  font-size: var(--text-xs);
  color: var(--danger);
  margin: 0;
  line-height: var(--leading-normal);
}
</style>
