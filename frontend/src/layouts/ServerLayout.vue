<script setup>
import AppSidebar from '../components/layout/AppSidebar.vue'
import AppTopbar from '../components/layout/AppTopbar.vue'

// Dummy props until Task 5 wires real state.
const dummyServerStatus = {
  status: 'stopped',
  loader: 'Fabric',
  version: '1.21.1'
}
const dummyActionState = { start: false, stop: false, restart: false }
</script>

<template>
  <div class="server-layout">
    <AppSidebar />
    <div class="server-layout__main">
      <AppTopbar
        :server-status="dummyServerStatus"
        status-label="Stopped"
        :action-state="dummyActionState"
        :start-locked="false"
        start-button-label="Start"
      />
      <main class="server-layout__content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.server-layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.server-layout__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.server-layout__content {
  flex: 1;
  padding: var(--space-5);
  overflow-y: auto;
}
</style>
