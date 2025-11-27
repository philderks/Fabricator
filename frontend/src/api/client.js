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

/**
 * Make an API request with error handling
 * @param {string} endpoint - API endpoint (e.g., '/api/status')
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
    
    // Parse response
    const data = await response.json().catch(() => ({}))
    
    // Handle non-OK responses
    if (!response.ok) {
      throw new ApiError(
        data.error || data.message || `Request failed with status ${response.status}`,
        response.status,
        data
      )
    }
    
    return data
  } catch (error) {
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
 */
export function get(endpoint, params = {}) {
  const queryString = new URLSearchParams(params).toString()
  const url = queryString ? `${endpoint}?${queryString}` : endpoint
  
  return apiRequest(url, {
    method: 'GET'
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
 * DELETE request helper
 */
export function del(endpoint) {
  return apiRequest(endpoint, {
    method: 'DELETE'
  })
}
