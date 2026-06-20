/**
 * Auth store (setup syntax, parallels stores/backups.js).
 *
 * `enabled` defaults to true (assume auth is on until /status says otherwise)
 * so that if the status call fails the router guard treats us as
 * unauthenticated and routes to /login — the safe default.
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getAuthStatus, postLogin, postLogout } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const enabled = ref(true)
  const isAuthenticated = ref(false)
  const checked = ref(false)
  const loading = ref(false)

  async function checkStatus() {
    // May throw on network failure — the caller (guard) handles it.
    const status = await getAuthStatus()
    enabled.value = Boolean(status.enabled)
    isAuthenticated.value = Boolean(status.authenticated)
    checked.value = true
    return status
  }

  async function login(password) {
    loading.value = true
    try {
      await postLogin(password)
      isAuthenticated.value = true
      checked.value = true
      return { ok: true }
    } catch (error) {
      isAuthenticated.value = false
      return { ok: false, error }
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await postLogout()
    } catch (_) {
      // Already logged out / network — local state is what matters.
    }
    isAuthenticated.value = false
  }

  function markUnauthenticated() {
    isAuthenticated.value = false
  }

  return { enabled, isAuthenticated, checked, loading, checkStatus, login, logout, markUnauthenticated }
})
