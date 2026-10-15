<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

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
    error.value = t('auth.change.tooShort', { min: MIN_LENGTH })
    return
  }
  if (next.value !== confirm.value) {
    error.value = t('auth.change.mismatch')
    return
  }
  submitting.value = true
  const res = await auth.changePassword(current.value, next.value)
  submitting.value = false
  if (res.ok) {
    toast.success(t('auth.change.success'), t('auth.toastTitle'))
    current.value = ''
    next.value = ''
    confirm.value = ''
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || t('auth.change.failed')
  }
}
</script>

<template>
  <Panel :title="$t('auth.password')">
    <form class="change-pw-form" @submit.prevent="onSubmit">
      <FormField :label="$t('auth.currentPassword')" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="current"
          type="password"
          class="change-pw-form__input"
          autocomplete="current-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField
        :label="$t('auth.newPassword')"
        :hint="$t('auth.minLengthHint', { min: MIN_LENGTH })"
        v-slot="{ id, describedBy }"
      >
        <input
          :id="id"
          v-model="next"
          type="password"
          class="change-pw-form__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <FormField :label="$t('auth.change.confirmNew')" v-slot="{ id, describedBy }">
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
          {{ $t('auth.change.submit') }}
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
