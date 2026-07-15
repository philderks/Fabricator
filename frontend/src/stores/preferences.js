/**
 * Client-side UI preferences (setup syntax).
 *
 * These are per-browser display choices that don't belong on the server: they
 * persist to localStorage so they survive reloads, and degrade gracefully to
 * in-memory defaults if storage is unavailable (private mode, quota, etc.).
 */

import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'fabricator.preferences'

function loadPersisted() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}
  } catch {
    return {}
  }
}

function persist(patch) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...loadPersisted(), ...patch })
    )
  } catch {
    // Best-effort: preferences are non-critical if storage is unavailable.
  }
}

export const usePreferencesStore = defineStore('preferences', () => {
  const persisted = loadPersisted()

  // CPU display mode:
  //   'average' — raw usage divided by core count, a 0–100% system-load figure
  //               like Windows Task Manager (the default).
  //   'total'   — the raw psutil figure, which can exceed 100% on multi-core
  //               hosts (e.g. 400% on 4 fully-loaded cores).
  const cpuDisplayMode = ref(
    persisted.cpuDisplayMode === 'total' ? 'total' : 'average'
  )
  watch(cpuDisplayMode, (mode) => persist({ cpuDisplayMode: mode }))

  return { cpuDisplayMode }
})
