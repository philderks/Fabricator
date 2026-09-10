import { ref, watch } from 'vue'

const STORAGE_KEY = 'fabricator.sidebarCollapsed'
const ROOT_CLASS = 'is-sidebar-collapsed'

const readStored = () => {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    // Blocked storage (private mode, cookies-off): not worth failing the
    // sidebar over — just start expanded.
    return false
  }
}

// Module-level, not component-level: AppSidebar is mounted by both RootLayout
// and ServerLayout, so navigating from the server list into a server remounts
// it. Component state would reset the rail to expanded on every such crossing.
const collapsed = ref(readStored())

// The collapse is published as a class on <html> rather than kept inside the
// component because --sidebar-width is a layout token other views measure
// against — ServerSettingsPage's footer is `position: fixed` with
// `left: var(--sidebar-width)`. Redefining the token under a root class means
// every one of those follows the rail for free, with no prop plumbing.
const syncRoot = (value) => {
  document.documentElement.classList.toggle(ROOT_CLASS, value)
}

syncRoot(collapsed.value)

watch(collapsed, (value) => {
  syncRoot(value)
  try {
    localStorage.setItem(STORAGE_KEY, String(value))
  } catch {
    // Same as readStored: the preference just doesn't persist this session.
  }
})

export function useSidebarCollapsed() {
  return {
    collapsed,
    toggle: () => { collapsed.value = !collapsed.value },
    expand: () => { collapsed.value = false }
  }
}
