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
            v-model="searchQuery"
            type="text"
            placeholder="Search modpacks..."
            @keyup.enter="performSearch"
          >
        </div>
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="loading || !searchQuery.trim()"
          @click="performSearch"
        >
          {{ loading ? 'Searching...' : 'Search' }}
        </button>
      </div>

      <div v-else class="search-row">
        <div class="search-bar">
          <input
            v-model="modpackLink"
            type="text"
            placeholder="https://modrinth.com/modpack/... or slug"
            @keyup.enter="resolveByLink"
          >
        </div>
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="resolving || !modpackLink.trim()"
          @click="resolveByLink"
        >
          {{ resolving ? 'Resolving...' : 'Resolve' }}
        </button>
      </div>

      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </div>

    <div v-if="loading" class="empty-state">
      <div class="spinner"></div>
      <p>Searching modpacks...</p>
    </div>

    <div v-else-if="results.length" class="results-grid">
      <button
        v-for="pack in results"
        :key="pack.project_id"
        type="button"
        class="modpack-card"
        :class="{
          selected: selectedModpack && selectedModpack.id === (pack.project_id || pack.id),
          installing: installing && selectedModpack && selectedModpack.id === (pack.project_id || pack.id)
        }"
        :disabled="installing"
        @click="selectPack(pack)"
      >
        <img
          :src="pack.icon_url || pack.iconUrl || 'https://via.placeholder.com/80?text=Pack'"
          :alt="pack.title || pack.name"
          class="modpack-icon"
        >
        <div class="modpack-info">
          <h3>{{ pack.title || pack.name || pack.slug }}</h3>
          <p>{{ truncate(pack.description, 120) }}</p>
          <span class="meta">{{ formatNumber(pack.downloads || 0) }} downloads</span>
        </div>
        <div
          v-if="installing && selectedModpack && selectedModpack.id === (pack.project_id || pack.id)"
          class="installing-indicator"
        >
          <div class="spinner"></div>
        </div>
      </button>
    </div>

    <div v-else class="empty-state">
      <p v-if="importMethod === 'search'">Search for modpacks compatible with {{ mcVersion }}.</p>
      <p v-else>Paste a Modrinth modpack link or slug to resolve it.</p>
    </div>

    <template #footer>
      <button class="btn btn-secondary" :disabled="installing" @click="$emit('close')">Close</button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'
import { getProjectDetails, searchModpacks } from '../../api/modrinth'

export default {
  name: 'ModpackBrowserModal',
  components: {
    BaseModal
  },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    mcVersion: {
      type: String,
      default: ''
    },
    loader: {
      type: String,
      default: 'fabric'
    },
    installing: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'install'],
  data() {
    return {
      importMethod: 'search',
      searchQuery: '',
      modpackLink: '',
      sortBy: 'downloads',
      loading: false,
      resolving: false,
      errorMessage: '',
      results: [],
      selectedModpack: null
    }
  },
  computed: {
    loaderLabel() {
      const value = (this.loader || 'fabric').toLowerCase()
      return value.charAt(0).toUpperCase() + value.slice(1)
    }
  },
  watch: {
    show(next) {
      if (!next) {
        this.resetState()
      }
    }
  },
  methods: {
    resetState() {
      this.importMethod = 'search'
      this.searchQuery = ''
      this.modpackLink = ''
      this.sortBy = 'downloads'
      this.loading = false
      this.resolving = false
      this.errorMessage = ''
      this.results = []
      this.selectedModpack = null
    },

    normalize(project) {
      return {
        id: project.project_id || project.id,
        slug: project.slug || '',
        title: project.title || project.name || project.slug || 'Unknown Modpack',
        description: project.description || '',
        downloads: project.downloads || 0,
        iconUrl: project.icon_url || '',
        projectType: project.project_type || 'modpack'
      }
    },

    parseProjectRef(input) {
      const raw = (input || '').trim()
      if (!raw) {
        return ''
      }

      if (!raw.startsWith('http://') && !raw.startsWith('https://')) {
        return raw.replace(/^@/, '')
      }

      try {
        const parsed = new URL(raw)
        const parts = parsed.pathname.split('/').filter(Boolean)
        if ((parts[0] === 'modpack' || parts[0] === 'project') && parts[1]) {
          return parts[1]
        }
        return parts[parts.length - 1] || ''
      } catch {
        return ''
      }
    },

    async performSearch() {
      const query = this.searchQuery.trim()
      if (!query) {
        this.results = []
        return
      }

      this.loading = true
      this.errorMessage = ''
      try {
        const response = await searchModpacks({
          query,
          version: this.mcVersion,
          loader: this.loader,
          sort: this.sortBy,
          limit: 12
        })
        this.results = Array.isArray(response.hits) ? response.hits : []
      } catch (error) {
        this.results = []
        this.errorMessage = error.message || 'Failed to search modpacks.'
      } finally {
        this.loading = false
      }
    },

    async resolveByLink() {
      const projectRef = this.parseProjectRef(this.modpackLink)
      if (!projectRef) {
        this.errorMessage = 'Enter a valid Modrinth modpack link, slug, or project ID.'
        return
      }

      this.resolving = true
      this.errorMessage = ''
      try {
        const project = await getProjectDetails(projectRef)
        if (project.project_type !== 'modpack') {
          this.errorMessage = 'This project exists but is not a modpack.'
          return
        }

        this.results = [project]
        this.selectPack(project)
      } catch (error) {
        this.errorMessage = error.message || 'Could not resolve modpack from link.'
      } finally {
        this.resolving = false
      }
    },

    selectPack(pack) {
      if (this.installing) return
      this.selectedModpack = this.normalize(pack)
      this.$emit('install', {
        projectId: this.selectedModpack.id,
        title: this.selectedModpack.title,
        mcVersion: this.mcVersion,
        loader: (this.loader || 'fabric').toLowerCase(),
      })
    },

    truncate(text, length = 100) {
      if (!text) {
        return ''
      }
      return text.length > length ? `${text.slice(0, length)}...` : text
    },

    formatNumber(value) {
      return new Intl.NumberFormat().format(value || 0)
    }
  }
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

.modpack-card.installing {
  opacity: 0.8;
  cursor: wait;
}

.installing-indicator {
  display: flex;
  align-items: center;
  margin-left: auto;
  flex-shrink: 0;
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
