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
        <AppButton
          variant="ghost"
          size="md"
          :disabled="imp.loading.value || !imp.searchQuery.value.trim()"
          @click="imp.performSearch()"
        >
          {{ imp.loading.value ? 'Searching...' : 'Search' }}
        </AppButton>
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
        <AppButton
          variant="ghost"
          size="md"
          :disabled="imp.resolving.value || !imp.modpackLink.value.trim()"
          @click="imp.resolveByLink()"
        >
          {{ imp.resolving.value ? 'Resolving...' : 'Resolve' }}
        </AppButton>
      </div>

      <p v-if="imp.errorMessage.value" class="error-text">{{ imp.errorMessage.value }}</p>
    </div>

    <div v-if="imp.loading.value" class="loading-state">
      <div class="spinner"></div>
      <p>Searching modpacks...</p>
    </div>

    <div v-else-if="imp.searchResults.value.length" class="results-grid">
      <SearchResultCard
        v-for="pack in imp.searchResults.value"
        :key="pack.project_id || pack.id"
        :icon-url="pack.icon_url || pack.iconUrl || null"
        :title="pack.title || pack.name || pack.slug"
        :description="truncate(pack.description, 120)"
        :meta="formatModpackMeta(pack)"
        :selected="imp.selectedModpack.value && imp.selectedModpack.value.id === (pack.project_id || pack.id)"
        @click="handleSelectPack(pack)"
      >
        <AppButton
          variant="primary"
          size="sm"
          @click.stop="handleInstallPack(pack)"
        >
          Install
        </AppButton>
      </SearchResultCard>
    </div>

    <div v-else class="modpack-browser-empty">
      <svg class="modpack-browser-empty__icon" width="64" height="64" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M9 9H15M9 13H13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3 class="modpack-browser-empty__heading" v-if="importMethod === 'search'">Search for modpacks</h3>
      <h3 class="modpack-browser-empty__heading" v-else>Resolve a modpack link</h3>
      <p class="modpack-browser-empty__body" v-if="importMethod === 'search'">
        Search for modpacks compatible with {{ mcVersion }}.
      </p>
      <p class="modpack-browser-empty__body" v-else>
        Paste a Modrinth modpack link or slug to resolve it.
      </p>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" @click="$emit('close')">Close</AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="!imp.selectedModpack.value"
        @click="confirmInstall"
      >
        Install Selected Modpack
      </AppButton>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import SearchResultCard from '../ui/SearchResultCard.vue'
import AppButton from '../ui/AppButton.vue'
import { useModpackImport } from '../../composables/useModpackImport'

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

function handleInstallPack(pack) {
  imp.selectPack(pack)
  confirmInstall()
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

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

// Modrinth tags loader compatibility as ordinary categories ('fabric',
// 'forge', 'neoforge', 'quilt'). Multi-loader packs are tagged with all
// four, so the alphabetical first three would read "fabric, forge, …" —
// regardless of which loader the user is actually browsing for, leaving
// the impression that the search is dominated by Fabric packs. Strip
// loader tags here; the active loader is already shown in the filter chip.
const LOADER_TAGS = new Set(['fabric', 'forge', 'neoforge', 'quilt'])

function formatModpackMeta(pack) {
  const parts = []
  if (pack.downloads) parts.push(`${formatNumber(pack.downloads)} downloads`)
  if (pack.categories && pack.categories.length) {
    const nonLoader = pack.categories.filter((c) => !LOADER_TAGS.has(String(c).toLowerCase()))
    if (nonLoader.length) {
      parts.push(nonLoader.slice(0, 3).join(', '))
    }
  }
  return parts.join(' · ')
}
</script>

<style scoped>
.search-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.filter-chip {
  align-self: flex-start;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.import-method {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.choice-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  cursor: pointer;
}

.search-row {
  display: flex;
  gap: var(--space-3);
}

.search-bar {
  flex: 1;
}

.search-bar input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: border-color 0.15s ease;
}

.search-bar input:focus {
  outline: none;
  border-color: var(--primary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: modpack-browser-spin 0.8s linear infinite;
}

@keyframes modpack-browser-spin {
  to {
    transform: rotate(360deg);
  }
}

.results-grid {
  display: grid;
  gap: var(--space-3);
  max-height: 500px;
  overflow-y: auto;
  padding: var(--space-1);
}

.results-grid::-webkit-scrollbar {
  width: 8px;
}

.results-grid::-webkit-scrollbar-track {
  background: var(--bg-primary);
  border-radius: var(--radius-sm);
}

.results-grid::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: var(--radius-sm);
}

.results-grid::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

.modpack-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-10) 0;
  color: var(--text-muted);
  text-align: center;
}

.modpack-browser-empty__icon {
  color: var(--text-disabled);
}

.modpack-browser-empty__heading {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-secondary);
  line-height: var(--leading-tight);
}

.modpack-browser-empty__body {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.error-text {
  margin: 0;
  color: var(--danger);
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .search-row {
    flex-direction: column;
  }
}
</style>
