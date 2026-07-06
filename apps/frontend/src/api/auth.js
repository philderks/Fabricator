import { apiRequest, get } from './client'

export function getAuthStatus() {
  return get('/api/auth/status')
}

export function postLogin(password) {
  // skipAuthRedirect: a wrong-password 401 is shown by the login view, not the
  // global session-expiry redirect.
  return apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
    skipAuthRedirect: true
  })
}

export function postLogout() {
  return apiRequest('/api/auth/logout', { method: 'POST' })
}

export function postSetup(password) {
  // First-boot credential. A JSON body is required by the server (CSRF guard).
  return apiRequest('/api/auth/setup', {
    method: 'POST',
    body: JSON.stringify({ password }),
    skipAuthRedirect: true
  })
}

export function postChangePassword(current, next) {
  // skipAuthRedirect: a wrong-current 401 is shown in the modal, it must NOT
  // trigger the global session-expiry redirect (that would log the user out).
  return apiRequest('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current, new: next }),
    skipAuthRedirect: true
  })
}
