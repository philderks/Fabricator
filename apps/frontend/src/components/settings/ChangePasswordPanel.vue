<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'

const MIN_LENGTH = 8

const auth = useAuthStore()
const toast = useToast()

const current = ref('')
const next = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)

async function onSubmit() {
  if (submitting.value) return
  error.value = ''
  if (next.value.length < MIN_LENGTH) {
    error.value = `New password must be at least ${MIN_LENGTH} characters.`
    return
  }
  if (next.value !== confirm.value) {
    error.value = 'New passwords do not match.'
    return
  }
  submitting.value = true
  const res = await auth.changePassword(current.value, next.value)
  submitting.value = false
  if (res.ok) {
    toast.success('Password changed', 'Authentication')
    current.value = ''
    next.value = ''
    confirm.value = ''
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || 'Could not change the password.'
  }
}
</script>

<template>
  <Panel title="Password">
    <form class="change-pw-form" @submit.prevent="onSubmit">
      <FormField label="Current password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="current"
          type="password"
          class="change-pw-form__input"
          autocomplete="current-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField label="New password" hint="At least 8 characters." v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="next"
          type="password"
          class="change-pw-form__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField label="Confirm new password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="confirm"
          type="password"
          class="change-pw-form__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <p v-if="error" class="change-pw-form__error" role="alert">{{ error }}</p>
      <div class="change-pw-form__actions">
        <AppButton type="submit" variant="primary" size="md" :loading="submitting">
          Change password
        </AppButton>
      </div>
    </form>
  </Panel>
</template>

<style scoped>
.change-pw-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 360px;
}

.change-pw-form__input {
  width: 100%;
}

.change-pw-form__error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--danger);
}

.change-pw-form__actions {
  display: flex;
}
</style>
