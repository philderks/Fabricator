/**
 * Auth store (setup syntax, parallels stores/backups.js).
 *
 * `enabled` defaults to true (assume auth is on until /status says otherwise)
 * so that if the status call fails the router guard treats us as
 * unauthenticated and routes to /login — the safe default. `needsSetup`
 * defaults false so a failed status check falls through to the login path
 * rather than the setup page.
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  getAuthStatus,
  postLogin,
  postLogout,
  postSetup,
  postChangePassword,
  postDisablePassword,
  postEnablePassword
} from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const enabled = ref(true)
  const isAuthenticated = ref(false)
  const needsSetup = ref(false)
  // Managed-hosting mode (fleet). Absent field (older backend / SPA-ahead
  // version skew) is treated as MANAGED — the fail-safe direction, since a
  // wrongly-unmanaged UI would expose deployment-owned controls.
  const managed = ref(false)
  const checked = ref(false)
  const loading = ref(false)

  async function checkStatus() {
    // May throw on network failure — the caller (guard) handles it.
    const status = await getAuthStatus()
    enabled.value = Boolean(status.enabled)
    isAuthenticated.value = Boolean(status.authenticated)
    needsSetup.value = Boolean(status.needs_setup)
    // Safe-default idiom (like playit binary_trust / players onlineMode): a
    // missing field defaults to managed, not unmanaged.
    managed.value = status.managed !== false
    checked.value = true
    return status
  }

  async function setup(password) {
    loading.value = true
    try {
      await postSetup(password)
      // Setup logs us in server-side; reflect that locally.
      isAuthenticated.value = true
      needsSetup.value = false
      checked.value = true
      return { ok: true }
    } catch (error) {
      return { ok: false, error }
    } finally {
      loading.value = false
    }
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

  async function changePassword(currentPassword, newPassword) {
    // The session stays valid (same signing key) — no local state change.
    try {
      await postChangePassword(currentPassword, newPassword)
      return { ok: true }
    } catch (error) {
      return { ok: false, error }
    }
  }

  async function disablePassword(currentPassword) {
    try {
      await postDisablePassword(currentPassword)
      // The server cleared the session, but with auth off there is nothing to
      // be authenticated against — reflect both so the router guard doesn't
      // bounce to /login for a now-open install.
      enabled.value = false
      isAuthenticated.value = false
      needsSetup.value = false
      return { ok: true }
    } catch (error) {
      return { ok: false, error }
    }
  }

  async function enablePassword(newPassword) {
    try {
      await postEnablePassword(newPassword)
      // The server logs us in as part of enabling, so we stay where we are
      // rather than being thrown to the login page.
      enabled.value = true
      isAuthenticated.value = true
      needsSetup.value = false
      return { ok: true }
    } catch (error) {
      return { ok: false, error }
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

  return {
    enabled,
    isAuthenticated,
    needsSetup,
    managed,
    checked,
    loading,
    checkStatus,
    setup,
    login,
    changePassword,
    disablePassword,
    enablePassword,
    logout,
    markUnauthenticated
  }
})
