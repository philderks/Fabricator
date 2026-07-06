<script setup>
import { provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import ToastContainer from './components/common/ToastContainer.vue'
import ServerCreateModal from './components/modals/ServerCreateModal.vue'
import { useToast } from './composables/useToast'

const router = useRouter()
const toast = useToast()

// Single writable ref provided down to consumers. Both AppSidebar's
// "No servers yet" chip / ServerSwitcher "Add server" item and Servers.vue's
// empty-state CTA flip this open. Hoisted to App.vue so the modal is
// available regardless of which layout is active.
const showCreateModal = ref(false)
provide('showCreateModal', showCreateModal)

const handleCreateServer = (createdServer) => {
  if (!createdServer) return
  const modpackTitle = createdServer.modpackSelection?.title
  const modpackInstallError = createdServer.modpackInstallError
  if (modpackInstallError) {
    toast.warning(
      `Server "${createdServer.name}" was created, but modpack install failed: ${modpackInstallError}`,
      'Modpack Install Failed'
    )
  } else {
    const message = modpackTitle
      ? `Server "${createdServer.name}" created. Selected modpack: ${modpackTitle}.`
      : `Server "${createdServer.name}" created successfully!`
    toast.success(message, 'Server Created')
  }

  // Always navigate to the new server's overview — works from "/" (where
  // the empty state was the only thing visible) and from any other server's
  // page (a switch to the new context).
  if (createdServer.id) {
    router.push({ name: 'ServerOverview', params: { id: createdServer.id } })
  }
}
</script>

<template>
  <router-view />
  <ServerCreateModal
    :show="showCreateModal"
    @close="showCreateModal = false"
    @create="handleCreateServer"
  />
  <ToastContainer />
</template>

