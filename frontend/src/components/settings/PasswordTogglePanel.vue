<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

const MIN_LENGTH = 8

const auth = useAuthStore()
const toast = useToast()

const current = ref('')
const next = ref('')
const error = ref('')
const submitting = ref(false)
const showConfirm = ref(false)

// The password is typed before the confirm, not after: the dialog is there to
// make sure the consequence registered, and asking first would let someone
// accept it and then find they cannot complete the action anyway.
function requestDisable() {
  error.value = ''
  if (!current.value) {
    error.value = t('auth.toggle.enterCurrent')
    return
  }
  showConfirm.value = true
}

async function onDisableConfirmed() {
  showConfirm.value = false
  if (submitting.value) return
  submitting.value = true
  const res = await auth.disablePassword(current.value)
  submitting.value = false
  if (res.ok) {
    current.value = ''
    toast.success(t('auth.toggle.offSuccess'), t('auth.toastTitle'))
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || t('auth.toggle.offFailed')
  }
}

async function onEnable() {
  if (submitting.value) return
  error.value = ''
  if (next.value.length < MIN_LENGTH) {
    error.value = t('auth.tooShort', { min: MIN_LENGTH })
    return
  }
  submitting.value = true
  const res = await auth.enablePassword(next.value)
  submitting.value = false
  if (res.ok) {
    next.value = ''
    toast.success(t('auth.toggle.onSuccess'), t('auth.toastTitle'))
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || t('auth.toggle.onFailed')
  }
}
</script>

<template>
  <Panel :title="auth.enabled ? $t('auth.toggle.titleOn') : $t('auth.password')">
    <!-- ON: offer to turn it off, current password required. -->
    <form v-if="auth.enabled" class="pw-toggle" @submit.prevent="requestDisable">
      <p class="pw-toggle__intro">{{ $t('auth.toggle.introOn') }}</p>
      <FormField
        :label="$t('auth.currentPassword')"
        :hint="$t('auth.toggle.currentHint')"
        v-slot="{ id, describedBy }"
      >
        <input
          :id="id"
          v-model="current"
          type="password"
          class="pw-toggle__input"
          autocomplete="current-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <p v-if="error" class="pw-toggle__error" role="alert">{{ error }}</p>
      <div class="pw-toggle__actions">
        <AppButton type="submit" variant="danger" :loading="submitting" :disabled="submitting">
          {{ $t('auth.toggle.turnOff') }}
        </AppButton>
      </div>
    </form>

    <!-- OFF: the way back. Setting a password is what turns auth on again. -->
    <form v-else class="pw-toggle" @submit.prevent="onEnable">
      <p class="pw-toggle__intro pw-toggle__intro--warning">{{ $t('auth.toggle.introOff') }}</p>
      <FormField
        :label="$t('auth.newPassword')"
        :hint="$t('auth.minLengthHint', { min: MIN_LENGTH })"
        v-slot="{ id, describedBy }"
      >
        <input
          :id="id"
          v-model="next"
          type="password"
          class="pw-toggle__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>
      <p v-if="error" class="pw-toggle__error" role="alert">{{ error }}</p>
      <div class="pw-toggle__actions">
        <AppButton type="submit" variant="primary" :loading="submitting" :disabled="submitting">
          {{ $t('auth.toggle.turnOn') }}
        </AppButton>
      </div>
    </form>

    <ConfirmModal
      :show="showConfirm"
      :title="$t('auth.toggle.confirmTitle')"
      :message="$t('auth.toggle.confirmMessage')"
      :description="$t('auth.toggle.confirmDescription')"
      type="warning"
      :confirm-text="$t('auth.toggle.turnOff')"
      :cancel-text="$t('auth.toggle.keep')"
      @confirm="onDisableConfirmed"
      @cancel="showConfirm = false"
    />
  </Panel>
</template>

<style scoped>
.pw-toggle {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pw-toggle__intro {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.pw-toggle__intro--warning {
  color: var(--warning);
}

.pw-toggle__input {
  width: 100%;
  /* Matches ChangePasswordPanel's field width — otherwise this input alone
     stretches to the full reading column while its sibling section's fields
     stay narrow, which reads as broken on wide panels. */
  max-width: 360px;
}

.pw-toggle__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--danger);
  line-height: var(--leading-normal);
}

.pw-toggle__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
