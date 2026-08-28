<script setup>
import AppSidebar from '../components/layout/AppSidebar.vue'
import MobileMenuButton from '../components/layout/MobileMenuButton.vue'

// `showCreateModal` is provided at the App.vue level so the create-server
// modal works from any layout/route (e.g. ServerSwitcher's "Add server").
// Account actions (change password / log out) live in AppSidebar so they
// are reachable on every authenticated page, including server pages.
</script>

<template>
  <div class="root-layout">
    <AppSidebar />
    <div class="root-layout__main">
      <!-- Mobile only. These routes have no AppTopbar (that one belongs to
           ServerLayout), so without a header here the drawer — and with it all
           navigation — would be unreachable from the server list and the
           server-less Settings page. -->
      <header class="root-layout__mobile-header">
        <MobileMenuButton />
        <span class="root-layout__mobile-brand">Fabricator</span>
      </header>
      <main class="root-layout__content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.root-layout {
  display: flex;
  /* dvh over vh so the layout ends at the visible viewport on mobile browsers
     rather than under the collapsing address bar. */
  min-height: 100dvh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.root-layout__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.root-layout__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-y: auto;
}

.root-layout__mobile-header {
  display: none;
}

@media (max-width: 768px) {
  .root-layout__mobile-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--app-chrome-header-height);
    padding: 0 var(--space-3);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .root-layout__mobile-brand {
    font-size: var(--text-md);
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.3px;
  }
}
</style>
