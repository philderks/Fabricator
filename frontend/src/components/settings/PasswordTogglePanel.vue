<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { useAuthStore } from '../../stores/auth'
import { useToast } from '../../composables/useToast'

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
    error.value = 'Enter your current password to turn the password off.'
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
    toast.success('Password turned off. Fabricator no longer asks for one.', 'Authentication')
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || 'Could not turn the password off.'
  }
}

async function onEnable() {
  if (submitting.value) return
  error.value = ''
  if (next.value.length < MIN_LENGTH) {
    error.value = `Password must be at least ${MIN_LENGTH} characters.`
    return
  }
  submitting.value = true
  const res = await auth.enablePassword(next.value)
  submitting.value = false
  if (res.ok) {
    next.value = ''
    toast.success('Password turned on.', 'Authentication')
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || 'Could not turn the password on.'
  }
}
</script>

<template>
  <Panel :title="auth.enabled ? 'Turn off password' : 'Password'">
    <!-- ON: offer to turn it off, current password required. -->
    <form v-if="auth.enabled" class="pw-toggle" @submit.prevent="requestDisable">
      <p class="pw-toggle__intro">
        Fabricator asks for a password before anyone can manage your servers.
        Turning it off removes that check for everyone who can reach this page.
      </p>
      <FormField
        label="Current password"
        hint="Required — this confirms it is you turning the password off."
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
          Turn off password
        </AppButton>
      </div>
    </form>

    <!-- OFF: the way back. Setting a password is what turns auth on again. -->
    <form v-else class="pw-toggle" @submit.prevent="onEnable">
      <p class="pw-toggle__intro pw-toggle__intro--warning">
        Fabricator is not asking for a password. Anyone who can reach this page
        can manage your servers.
      </p>
      <FormField label="New password" hint="At least 8 characters." v-slot="{ id, describedBy }">
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
          Turn on password
        </AppButton>
      </div>
    </form>

    <ConfirmModal
      :show="showConfirm"
      title="Turn off the password?"
      message="Fabricator will stop asking for a password."
      description="Anyone who can reach this address will be able to manage your servers, read the console, and edit files. Only do this on a network you trust. You can set a password again from this page."
      type="warning"
      confirm-text="Turn off password"
      cancel-text="Keep password"
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
