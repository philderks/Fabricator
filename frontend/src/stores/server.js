import { defineStore } from 'pinia'
import { ref } from 'vue'

// The full store is built in Task 2. This skeleton exists only to confirm
// Pinia registration works and the import path resolves.
export const useServerStore = defineStore('server', () => {
  const _placeholder = ref(null)

  return {
    _placeholder
  }
})
