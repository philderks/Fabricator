<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppButton from '../components/ui/AppButton.vue'
import FormField from '../components/ui/FormField.vue'

const MIN_LENGTH = 8

const auth = useAuthStore()
const router = useRouter()

const password = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)
const passwordInput = ref(null)

onMounted(() => passwordInput.value?.focus())

async function onSubmit() {
  if (submitting.value) return
  error.value = ''
  if (password.value.length < MIN_LENGTH) {
    error.value = `Password must be at least ${MIN_LENGTH} characters.`
    return
  }
  if (password.value !== confirm.value) {
    error.value = 'Passwords do not match.'
    return
  }
  submitting.value = true
  const res = await auth.setup(password.value)
  submitting.value = false
  if (res.ok) {
    router.replace('/')
  } else {
    error.value =
      res.error?.data?.error || res.error?.message || 'Setup failed. Please try again.'
    password.value = ''
    confirm.value = ''
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <img class="login-card__logo" src="/favicon.svg" alt="" />
      <h1 class="login-card__title">Welcome to Fabricator</h1>
      <p class="login-card__subtitle">Set an operator password to secure the panel.</p>

      <FormField label="Password" hint="At least 8 characters." v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="password"
          type="password"
          class="login-card__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
          ref="passwordInput"
        />
      </FormField>

      <FormField label="Confirm password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="confirm"
          type="password"
          class="login-card__input"
          autocomplete="new-password"
          :aria-describedby="describedBy"
        />
      </FormField>

      <p v-if="error" class="login-card__error" role="alert">{{ error }}</p>

      <AppButton type="submit" variant="primary" size="md" :loading="submitting">
        Create password
      </AppButton>
    </form>
  </div>
</template>

<style scoped>
/* Mirrors LoginPage's centered card. */
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: var(--space-5);
}

.login-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 340px;
  padding: var(--space-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
}

.login-card__logo {
  width: 48px;
  height: 48px;
  align-self: center;
}

.login-card__title {
  margin: 0;
  text-align: center;
  font-size: var(--text-lg);
}

.login-card__subtitle {
  margin: 0;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.login-card__input {
  width: 100%;
}

.login-card__error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--danger);
}
</style>
