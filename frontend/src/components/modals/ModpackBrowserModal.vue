<template>
  <BaseModal
    :show="show"
    title="Browse Modpacks"
    size="xlarge"
    @close="$emit('close')"
  >
    <div class="search-section">
      <div class="filter-chip">
        Filtered to Minecraft {{ mcVersion }} ({{ loaderLabel }})
      </div>

      <div class="import-method">
        <label class="choice-pill">
          <input type="radio" v-model="importMethod" value="search">
          <span>Search</span>
        </label>
        <label class="choice-pill">
          <input type="radio" v-model="importMethod" value="link">
          <span>Link</span>
        </label>
      </div>

      <div v-if="importMethod === 'search'" class="search-row">
        <div class="search-bar">
          <input
            v-model="imp.searchQuery.value"
            type="text"
            placeholder="Search modpacks..."
            @keyup.enter="imp.performSearch()"
          >
        </div>
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="imp.loading.value || !imp.searchQuery.value.trim()"
          @click="imp.performSearch()"
        >
          {{ imp.loading.value ? 'Searching...' : 'Search' }}
        </button>
      </div>

      <div v-else class="search-row">
        <div class="search-bar">
          <input
            v-model="imp.modpackLink.value"
            type="text"
            placeholder="https://modrinth.com/modpack/... or slug"
            @keyup.enter="imp.resolveByLink()"
          >
        </div>
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="imp.resolving.value || !imp.modpackLink.value.trim()"
          @click="imp.resolveByLink()"
        >
          {{ imp.resolving.value ? 'Resolving...' : 'Resolve' }}
        </button>
      </div>

      <p v-if="imp.errorMessage.value" class="error-text">{{ imp.errorMessage.value }}</p>
    </div>

    <div v-if="imp.loading.value" class="empty-state">
      <div class="spinner"></div>
      <p>Searching modpacks...</p>
    </div>

    <div v-else-if="imp.searchResults.value.length" class="results-grid">
      <button
        v-for="pack in imp.searchResults.value"
        :key="pack.project_id"
        type="button"
        class="modpack-card"
        :class="{
          selected: imp.selectedModpack.value && imp.selectedModpack.value.id === (pack.project_id || pack.id),
        }"
        @click="handleSelectPack(pack)"
      >
        <img
          :src="pack.icon_url || pack.iconUrl || 'https://via.placeholder.com/80?text=Pack'"
          :alt="pack.title || pack.name"
          class="modpack-icon"
        >
        <div class="modpack-info">
          <h3>{{ pack.title || pack.name || pack.slug }}</h3>
          <p>{{ truncate(pack.description, 120) }}</p>
          <span class="meta">{{ formatDownloads(pack.downloads || 0) }} downloads</span>
        </div>
      </button>
    </div>

    <div v-else class="empty-state">
      <p v-if="importMethod === 'search'">Search for modpacks compatible with {{ mcVersion }}.</p>
      <p v-else>Paste a Modrinth modpack link or slug to resolve it.</p>
    </div>

    <template #footer>
      <button class="btn btn-secondary" @click="$emit('close')">Close</button>
      <button
        class="btn btn-primary"
        :disabled="!imp.selectedModpack.value"
        @click="confirmInstall"
      >
        Install Selected Modpack
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import { useModpackImport, formatDownloads } from '../../composables/useModpackImport'

const props = defineProps({
  show: { type: Boolean, required: true },
  mcVersion: { type: String, default: '' },
  loader: { type: String, default: 'fabric' },
})

const emit = defineEmits(['close', 'install'])

const importMethod = ref('search')

const loaderLabel = computed(() => {
  const value = (props.loader || 'fabric').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
})

const imp = useModpackImport({
  mcVersion: () => props.mcVersion,
  loader: () => props.loader
})

watch(() => props.show, (next) => {
  if (!next) {
    importMethod.value = 'search'
    imp.resetAll()
  }
})

function handleSelectPack(pack) {
  imp.selectPack(pack)
}

function confirmInstall() {
  if (!imp.selectedModpack.value) {
    return
  }
  emit('install', {
    projectId: imp.selectedModpack.value.id,
    title: imp.selectedModpack.value.title,
    mcVersion: props.mcVersion,
    loader: (props.loader || 'fabric').toLowerCase(),
  })
}

function truncate(text, length = 100) {
  if (!text) {
    return ''
  }
  return text.length > length ? `${text.slice(0, length)}...` : text
}
</script>

<style scoped>
.search-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.filter-chip {
  align-self: flex-start;
  padding: 0.3rem 0.6rem;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 0.78rem;
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.import-method {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.choice-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  padding: 0.35rem 0.7rem;
  font-size: 0.85rem;
}

.search-row {
  display: flex;
  gap: 0.75rem;
}

.search-bar {
  flex: 1;
}

.search-bar input {
  width: 100%;
  padding: 0.7rem 0.9rem;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 0.75rem;
}

.modpack-card {
  display: flex;
  gap: 0.75rem;
  align-items: start;
  width: 100%;
  text-align: left;
  padding: 0.8rem;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-primary);
  cursor: pointer;
}

.modpack-card:hover {
  border-color: color-mix(in oklch, var(--primary) 35%, var(--border-color));
}

.modpack-card.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--primary) 18%, transparent);
}


.modpack-icon {
  width: 56px;
  height: 56px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid var(--border-color);
}

.modpack-info h3 {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.modpack-info p {
  margin: 0.3rem 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.meta {
  color: var(--text-secondary);
  font-size: 0.78rem;
}

.empty-state {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  text-align: center;
}

.error-text {
  margin: 0;
  color: var(--danger, #d14343);
  font-size: 0.875rem;
}


.spinner {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid color-mix(in oklch, var(--primary) 25%, transparent);
  border-top-color: var(--primary);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}


@media (max-width: 768px) {
  .search-row {
    flex-direction: column;
  }
}
</style>
