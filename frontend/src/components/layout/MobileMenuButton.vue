<script setup>
import { useMobileNav } from '../../composables/useMobileNav'

// Shared by both chrome headers: AppTopbar on server routes, RootLayout's
// mobile header on the server-less ones. Below the breakpoint the sidebar is
// off-canvas, so without this button there is no way back to navigation.
const { drawerOpen, toggle } = useMobileNav()
</script>

<template>
  <button
    type="button"
    class="mobile-menu-btn"
    aria-label="Open navigation menu"
    aria-controls="app-sidebar"
    :aria-expanded="drawerOpen"
    @click="toggle"
  >
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
      <path d="M2.5 4.5h13M2.5 9h13M2.5 13.5h13"/>
    </svg>
  </button>
</template>

<style scoped>
/* Desktop keeps the sidebar in the flow, so the button has nothing to open.
   Hidden here rather than v-if'd on isMobile so the chrome doesn't reflow on
   the first tick before matchMedia has been read. */
.mobile-menu-btn {
  display: none;
}

@media (max-width: 768px) {
  .mobile-menu-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    /* 36px: comfortably past the 24px icon, still short of the 40px that would
       push the header row taller than --app-chrome-header-height. */
    width: 36px;
    height: 36px;
    margin-left: calc(var(--space-2) * -1);
    padding: 0;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;
  }

  .mobile-menu-btn:hover,
  .mobile-menu-btn[aria-expanded='true'] {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .mobile-menu-btn:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
  }
}
</style>
