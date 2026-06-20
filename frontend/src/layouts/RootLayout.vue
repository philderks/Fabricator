<script setup>
import AppSidebar from '../components/layout/AppSidebar.vue'
import { useRouter } from 'vue-router'
import AppButton from '../components/ui/AppButton.vue'
import { useAuthStore } from '../stores/auth'

// `showCreateModal` is provided at the App.vue level so the create-server
// modal works from any layout/route (e.g. ServerSwitcher's "Add server").

const auth = useAuthStore()
const router = useRouter()

async function onLogout() {
  await auth.logout()
  router.push({ name: 'Login' })
}
</script>

<template>
  <div class="root-layout">
    <AppSidebar />
    <main class="root-layout__content">
      <div v-if="auth.enabled" class="root-layout__topbar">
        <AppButton variant="ghost" size="sm" @click="onLogout">Log out</AppButton>
      </div>
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

.root-layout__topbar {
  display: flex;
  justify-content: flex-end;
  padding: var(--space-3) var(--space-4);
}
</style>
