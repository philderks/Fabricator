import { ref, watch } from 'vue'

/* Mobile navigation state.
 *
 * Below --breakpoint-mobile the sidebar leaves the document flow and becomes an
 * off-canvas drawer, so "is the viewport narrow" and "is the drawer open" are
 * app-wide facts rather than per-component ones: AppSidebar draws the drawer,
 * AppTopbar and RootLayout draw the button that opens it, and both layouts need
 * the same answer. Module-level state like useSidebarCollapsed — AppSidebar is
 * mounted by both layouts and remounts when crossing between them.
 *
 * The 768px threshold is duplicated in CSS (media queries can't read custom
 * properties); global.css marks its copy as the pair to this one.
 */
const MOBILE_QUERY = '(max-width: 768px)'
const ROOT_CLASS = 'is-mobile-drawer-open'

const isMobile = ref(false)
const drawerOpen = ref(false)

const close = () => { drawerOpen.value = false }
const open = () => { drawerOpen.value = true }
const toggle = () => { drawerOpen.value = !drawerOpen.value }

if (typeof window !== 'undefined' && window.matchMedia) {
  const mql = window.matchMedia(MOBILE_QUERY)
  isMobile.value = mql.matches
  mql.addEventListener('change', (event) => {
    isMobile.value = event.matches
    // Rotating to landscape / resizing past the breakpoint puts the sidebar
    // back in the flow; a drawer left "open" would then have the backdrop
    // covering a perfectly usable desktop layout.
    if (!event.matches) close()
  })
}

// Scroll lock lives on <html> rather than <body> because the scrolling element
// varies by page (ServerLayout scrolls its own __content); locking the root
// stops the rubber-band on iOS regardless of which one it is.
watch(drawerOpen, (isOpen) => {
  document.documentElement.classList.toggle(ROOT_CLASS, isOpen)

  // Escape closes, matching every other dismissible overlay in the app.
  if (isOpen) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

export function useMobileNav() {
  return { isMobile, drawerOpen, open, close, toggle }
}
