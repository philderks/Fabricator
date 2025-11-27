import { ref, reactive } from 'vue'

// Global toast state
const toasts = ref([])
let nextId = 1

/**
 * Composable for managing toast notifications
 * @returns {Object} Toast management functions
 */
export function useToast() {
  /**
   * Show a toast notification
   * @param {Object} options - Toast options
   * @param {string} options.message - Toast message
   * @param {string} options.type - Toast type (success, error, warning, info)
   * @param {string} options.title - Optional title
   * @param {number} options.duration - Duration in ms (default: 4000)
   * @param {boolean} options.autoClose - Auto close toast (default: true)
   */
  const showToast = (options) => {
    const toast = {
      id: nextId++,
      message: options.message || '',
      type: options.type || 'info',
      title: options.title || '',
      duration: options.duration || 4000,
      autoClose: options.autoClose !== false
    }
    
    toasts.value.push(toast)
    
    return toast.id
  }

  /**
   * Show a success toast
   * @param {string} message - Success message
   * @param {string} title - Optional title
   */
  const success = (message, title = '') => {
    return showToast({ message, title, type: 'success' })
  }

  /**
   * Show an error toast
   * @param {string} message - Error message
   * @param {string} title - Optional title
   */
  const error = (message, title = '') => {
    return showToast({ message, title, type: 'error', duration: 6000 })
  }

  /**
   * Show a warning toast
   * @param {string} message - Warning message
   * @param {string} title - Optional title
   */
  const warning = (message, title = '') => {
    return showToast({ message, title, type: 'warning' })
  }

  /**
   * Show an info toast
   * @param {string} message - Info message
   * @param {string} title - Optional title
   */
  const info = (message, title = '') => {
    return showToast({ message, title, type: 'info' })
  }

  /**
   * Remove a toast by ID
   * @param {number} id - Toast ID
   */
  const removeToast = (id) => {
    const index = toasts.value.findIndex(t => t.id === id)
    if (index !== -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Clear all toasts
   */
  const clearAll = () => {
    toasts.value = []
  }

  return {
    toasts,
    showToast,
    success,
    error,
    warning,
    info,
    removeToast,
    clearAll
  }
}
