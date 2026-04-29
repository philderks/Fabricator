<script setup>
import { provide, ref } from 'vue'
import RootTopbar from '../components/layout/RootTopbar.vue'

// Single writable ref provided down to consumers. RootTopbar flips it open
// from the topbar button; Servers.vue (the only child this layout serves)
// binds it to `<ServerCreateModal :show="...">` and writes false on close.
const showCreateModal = ref(false)
provide('showCreateModal', showCreateModal)

const handleAddServer = () => {
  showCreateModal.value = true
}
</script>

<template>
  <div class="root-layout">
    <RootTopbar @add-server="handleAddServer" />
    <main class="root-layout__content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.root-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.root-layout__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
</style>
