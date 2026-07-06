<script setup>
import AppSidebar from '../components/layout/AppSidebar.vue'

// `showCreateModal` is provided at the App.vue level so the create-server
// modal works from any layout/route (e.g. ServerSwitcher's "Add server").
// Account actions (change password / log out) live in AppSidebar so they
// are reachable on every authenticated page, including server pages.
</script>

<template>
  <div class="root-layout">
    <AppSidebar />
    <main class="root-layout__content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.root-layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.root-layout__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow-y: auto;
}
</style>
