<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppButton from '../components/ui/AppButton.vue'
import FormField from '../components/ui/FormField.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const password = ref('')
const error = ref('')
const submitting = ref(false)
const passwordInput = ref(null)

onMounted(() => passwordInput.value?.focus())

async function onSubmit() {
  if (submitting.value) return
  error.value = ''
  submitting.value = true
  const res = await auth.login(password.value)
  submitting.value = false
  if (res.ok) {
    // Only follow same-app absolute paths — reject protocol-relative (//evil.com)
    // and backslash forms so a crafted ?redirect= can't become an open redirect.
    const raw = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    const redirect = /^\/(?!\/)/.test(raw) && !raw.includes('\\') ? raw : '/'
    router.replace(redirect)
  } else {
    error.value =
      res.error?.status === 401
        ? 'Incorrect password.'
        : res.error?.message || 'Login failed. Please try again.'
    password.value = ''
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <img class="login-card__logo" src="/favicon.svg" alt="" />
      <h1 class="login-card__title">Fabricator</h1>
      <p class="login-card__subtitle">Enter the operator password to continue.</p>

      <FormField label="Password" v-slot="{ id, describedBy }">
        <input
          :id="id"
          v-model="password"
          type="password"
          class="login-card__input"
          autocomplete="current-password"
          :aria-describedby="describedBy"
          ref="passwordInput"
        />
      </FormField>

      <p v-if="error" class="login-card__error" role="alert">{{ error }}</p>

      <AppButton type="submit" variant="primary" size="md" :loading="submitting">
        Log in
      </AppButton>
    </form>
  </div>
</template>

<style scoped>
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
