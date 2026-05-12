<script setup>
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import AppButton from '../components/ui/AppButton.vue'
import { useToast } from '../composables/useToast'
import { useServerStore } from '../stores/server'

const router = useRouter()
const toast = useToast()
const store = useServerStore()

const loading = ref(true)
const errorMessage = ref(null)
// Provided by App.vue — AppSidebar's "No servers yet" chip and this page's
// empty-state CTA both flip the same ref open. The modal itself lives in
// App.vue so it works from every route.
const showCreateModal = inject('showCreateModal', ref(false))

const loadServers = async () => {
  loading.value = true
  errorMessage.value = null
  try {
    await store.loadServers()
    const list = store.serversList
    if (list.length > 0) {
      // Skip the empty state entirely — there's no list view here anymore,
      // so anyone landing on `/` with at least one server gets sent to the
      // first server's overview.
      router.replace({ name: 'ServerOverview', params: { id: list[0].id } })
    }
  } catch (error) {
    console.error('Failed to load servers:', error)
    errorMessage.value = error?.message || 'Failed to load servers'
    toast.error('Failed to load servers', 'Error')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadServers()
})
</script>

<template>
  <div class="servers-page">
    <div v-if="loading" class="servers-page__state">
      <div class="servers-page__spinner" aria-hidden="true"></div>
      <p>Loading servers…</p>
    </div>

    <div v-else-if="errorMessage" class="servers-page__state servers-page__state--error">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
        <path d="M12 8V13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        <circle cx="12" cy="16" r="0.9" fill="currentColor"/>
      </svg>
      <h3>Couldn't load servers</h3>
      <p>{{ errorMessage }}</p>
      <AppButton variant="ghost" size="md" @click="loadServers">Retry</AppButton>
    </div>

    <div v-else class="servers-page__empty">
      <img
        class="servers-page__hero"
        src="/favicon.svg"
        alt=""
        width="48"
        height="48"
        aria-hidden="true"
      />
      <h2 class="servers-page__title">No servers yet</h2>
      <p class="servers-page__subtitle">Create your first Minecraft server to get started.</p>
      <AppButton variant="primary" size="md" @click="showCreateModal = true">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M6 1v10M1 6h10"/>
        </svg>
        Create server
      </AppButton>
    </div>
  </div>
</template>

<style scoped>
.servers-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: var(--space-5);
}

.servers-page__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.servers-page__hero {
  display: block;
  margin-bottom: var(--space-6);
}

.servers-page__title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 600;
  color: #c8c8c8;
  letter-spacing: -0.3px;
}

.servers-page__subtitle {
  margin: 0 0 var(--space-6);
  font-size: var(--text-sm);
  color: #3a3a3a;
}

.servers-page__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  text-align: center;
  color: var(--text-muted);
}

.servers-page__state h3 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.servers-page__state p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  max-width: 360px;
}

.servers-page__state svg {
  color: var(--text-disabled);
}

.servers-page__state--error svg {
  color: var(--danger);
}

.servers-page__spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: servers-page-spin 0.8s linear infinite;
}

@keyframes servers-page-spin {
  to { transform: rotate(360deg); }
}
</style>
