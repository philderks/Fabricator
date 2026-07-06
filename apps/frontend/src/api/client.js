/**
 * Base API Client
 * Provides common utilities for API requests with error handling
 */

const API_BASE = '' // Use relative path since Vite proxy is configured

/**
 * Custom API Error class
 */
export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

// Global 401 handler, registered in main.js. Kept here (not importing the store
// or router) so this low-level module stays decoupled.
let unauthorizedHandler = null

export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

function notifyUnauthorized() {
  if (typeof unauthorizedHandler === 'function') {
    try {
      unauthorizedHandler()
    } catch (_) {
      // never let the handler break request error propagation
    }
  }
}

function extractErrorMessageFromBody(rawBody) {
  if (!rawBody) {
    return ''
  }

  // Remove HTML tags for Flask/Werkzeug error pages and collapse whitespace.
  const plain = String(rawBody)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!plain) {
    return ''
  }

  return plain.length > 220 ? `${plain.slice(0, 220)}...` : plain
}

/**
 * Make an API request with error handling
 * @param {string} endpoint - API endpoint (e.g., '/api/servers')
 * @param {Object} options - Fetch options
 * @returns {Promise<any>} Response data
 * @throws {ApiError} If request fails
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`
  
  // Default headers
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }
  
  try {
    const response = await fetch(url, {
      ...options,
      headers
    })
    
    // Parse response body as JSON when possible, otherwise keep text for diagnostics.
    const contentType = response.headers.get('content-type') || ''
    let data = {}
    let rawBody = ''

    if (contentType.includes('application/json')) {
      data = await response.json().catch(() => ({}))
    } else {
      rawBody = await response.text().catch(() => '')
    }
    
    // Handle non-OK responses
    if (!response.ok) {
      if (response.status === 401 && !options.skipAuthRedirect) {
        notifyUnauthorized()
      }
      const bodyMessage = extractErrorMessageFromBody(rawBody)
      throw new ApiError(
        data.error || data.message || bodyMessage || `Request failed with status ${response.status}`,
        response.status,
        data && Object.keys(data).length ? data : null
      )
    }
    
    return data
  } catch (error) {
    // Propagate AbortError untouched so callers can distinguish intentional
    // cancellation from real failures (don't toast/log abort as an error).
    if (error?.name === 'AbortError') {
      throw error
    }

    // Re-throw ApiError as-is
    if (error instanceof ApiError) {
      throw error
    }

    // Network or other errors
    throw new ApiError(
      error.message || 'Network error occurred',
      0,
      null
    )
  }
}

/**
 * GET request helper
 *
 * @param {string} endpoint
 * @param {Object} [params] - query parameters
 * @param {Object} [options] - request options
 * @param {AbortSignal} [options.signal] - forwarded to fetch for cancellation
 */
export function get(endpoint, params = {}, options = {}) {
  const queryString = new URLSearchParams(params).toString()
  const url = queryString ? `${endpoint}?${queryString}` : endpoint

  return apiRequest(url, {
    method: 'GET',
    signal: options.signal
  })
}

/**
 * POST request helper
 */
export function post(endpoint, data = {}) {
  return apiRequest(endpoint, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

/**
 * PUT request helper
 */
export function put(endpoint, data = {}) {
  return apiRequest(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

/**
 * PATCH request helper
 */
export function patch(endpoint, data = {}) {
  return apiRequest(endpoint, {
    method: 'PATCH',
    body: JSON.stringify(data)
  })
}

/**
 * DELETE request helper
 */
export function del(endpoint, data) {
  return apiRequest(endpoint, {
    method: 'DELETE',
    ...(data !== undefined ? { body: JSON.stringify(data) } : {})
  })
}
