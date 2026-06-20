<script setup>
import { ref, watch } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'

const MIN_LENGTH = 8

const props = defineProps({
  show: { type: Boolean, required: true }
})
const emit = defineEmits(['close'])

const auth = useAuthStore()
const toast = useToast()

const current = ref('')
const next = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)

function reset() {
  current.value = ''
  next.value = ''
  confirm.value = ''
  error.value = ''
  submitting.value = false
}

// Clear the form each time the modal opens.
watch(() => props.show, (open) => {
  if (open) reset()
})

function close() {
  if (submitting.value) return
  emit('close')
}

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
    emit('close')
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || 'Could not change the password.'
  }
}
</script>

<template>
  <BaseModal :show="show" title="Change password" size="small" @close="close">
    <form class="change-pw" @submit.prevent="onSubmit">
      <FormField label="Current password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="current"
          type="password"
          class="change-pw__input"
          autocomplete="current-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField label="New password" hint="At least 8 characters." v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="next"
          type="password"
          class="change-pw__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField label="Confirm new password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="confirm"
          type="password"
          class="change-pw__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <p v-if="error" class="change-pw__error" role="alert">{{ error }}</p>
      <!-- allow Enter to submit while focus is in a field -->
      <button type="submit" hidden></button>
    </form>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="submitting" @click="close">
        Cancel
      </AppButton>
      <AppButton variant="primary" size="md" :loading="submitting" @click="onSubmit">
        Change password
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.change-pw {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.change-pw__input {
  width: 100%;
}

.change-pw__error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--danger);
}
</style>
