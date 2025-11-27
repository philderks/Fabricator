<template>
  <BaseModal 
    :show="show" 
    title="Browse Mods" 
    size="xlarge"
    @close="$emit('close')"
  >
    <!-- Search Bar -->
    <div class="search-section">
      <div class="search-bar">
        <svg class="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="2"/>
          <path d="M14 14L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <input 
          v-model="searchQuery" 
          type="text" 
          placeholder="Search mods..."
          @input="debouncedSearch"
        >
      </div>
      
      <div class="filters">
        <select v-model="selectedLoader" @change="performSearch">
          <option value="">All Loaders</option>
          <option value="fabric">Fabric</option>
          <option value="forge">Forge</option>
          <option value="quilt">Quilt</option>
        </select>
        
        <select v-model="selectedVersion" @change="performSearch">
          <option value="">All Versions</option>
          <option value="1.20.4">1.20.4</option>
          <option value="1.20.1">1.20.1</option>
          <option value="1.19.4">1.19.4</option>
          <option value="1.19.2">1.19.2</option>
        </select>

        <select v-model="sortBy" @change="performSearch">
          <option value="relevance">Relevance</option>
          <option value="downloads">Downloads</option>
          <option value="updated">Updated</option>
          <option value="newest">Newest</option>
        </select>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Searching mods...</p>
    </div>

    <!-- Results -->
    <div v-else-if="results.length > 0" class="results-grid">
      <div 
        v-for="mod in results" 
        :key="mod.project_id"
        class="mod-card"
        @click="selectMod(mod)"
      >
        <img 
          :src="mod.icon_url || 'https://via.placeholder.com/80?text=No+Image'" 
          :alt="mod.title"
          class="mod-icon"
        >
        <div class="mod-info">
          <h3 class="mod-title">{{ mod.title }}</h3>
          <p class="mod-description">{{ truncate(mod.description, 100) }}</p>
          <div class="mod-stats">
            <span class="stat">
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                <path d="M10 2L3 7V17H8V12H12V17H17V7L10 2Z" stroke="currentColor" stroke-width="1.5"/>
              </svg>
              {{ formatNumber(mod.downloads) }}
            </span>
            <span class="stat">
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                <path d="M10 3V17M10 17L4 11M10 17L16 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              {{ mod.latest_version || 'N/A' }}
            </span>
          </div>
        </div>
        <div class="mod-actions">
          <button class="btn btn-primary btn-sm" @click.stop="installMod(mod)">
            Install
          </button>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="!loading && searchQuery" class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>
        <path d="M21 21L16.5 16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        <path d="M11 8V14M8 11H14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3>No mods found</h3>
      <p>Try adjusting your search or filters</p>
    </div>

    <!-- Initial State -->
    <div v-else class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M9 9H15M9 13H13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3>Search for mods</h3>
      <p>Start typing to find mods for your server</p>
    </div>

    <template #footer>
      <button class="btn btn-secondary" @click="$emit('close')">
        Close
      </button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'
import { searchMods } from '../../api/modrinth'

export default {
  name: 'ModBrowserModal',
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
      default: '1.20.1'
    },
    loader: {
      type: String,
      default: 'fabric'
    }
  },
  emits: ['close', 'install'],
  data() {
    return {
      searchQuery: '',
      selectedLoader: this.loader,
      selectedVersion: this.mcVersion,
      sortBy: 'relevance',
      results: [],
      loading: false,
      debounceTimeout: null
    };
  },
  methods: {
    debouncedSearch() {
      clearTimeout(this.debounceTimeout);
      this.debounceTimeout = setTimeout(() => {
        this.performSearch();
      }, 500);
    },
    
    async performSearch() {
      if (!this.searchQuery.trim()) {
        this.results = []
        return
      }

      this.loading = true
      
      try {
        const data = await searchMods({
          query: this.searchQuery,
          version: this.selectedVersion,
          loader: this.selectedLoader,
          sort: this.sortBy,
          limit: 20
        })
        
        this.results = data.hits || []
      } catch (error) {
        console.error('Search failed:', error)
        this.results = []
      } finally {
        this.loading = false
      }
    },

    async installMod(mod) {
      this.$emit('install', {
        modId: mod.project_id,
        modTitle: mod.title,
        mcVersion: this.selectedVersion || this.mcVersion,
        loader: this.selectedLoader || this.loader
      });
    },

    selectMod(mod) {
      // Future: Open mod details view
      console.log('Selected mod:', mod);
    },

    truncate(text, length) {
      if (!text) return '';
      return text.length > length ? text.substring(0, length) + '...' : text;
    },

    formatNumber(num) {
      if (!num) return '0';
      if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
      if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
      return num.toString();
    }
  },
  watch: {
    show(newVal) {
      if (!newVal) {
        // Reset on close
        this.searchQuery = '';
        this.results = [];
      }
    }
  }
}
</script>

<style scoped>
.search-section {
  margin-bottom: 24px;
}

.search-bar {
  position: relative;
  margin-bottom: 16px;
}

.search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
}

.search-bar input {
  width: 100%;
  padding: 12px 16px 12px 48px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9375rem;
  transition: all 0.2s;
}

.search-bar input:focus {
  outline: none;
  border-color: var(--primary);
}

.filters {
  display: flex;
  gap: 12px;
}

.filters select {
  flex: 1;
  padding: 10px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filters select:focus {
  outline: none;
  border-color: var(--primary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: btn-spin 0.8s linear infinite;
  margin-bottom: 16px;
}

.results-grid {
  display: grid;
  gap: 16px;
  max-height: 500px;
  overflow-y: auto;
  padding: 4px;
}

.mod-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.mod-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
}

.mod-icon {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}

.mod-info {
  flex: 1;
  min-width: 0;
}

.mod-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mod-description {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.mod-stats {
  display: flex;
  gap: 16px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8125rem;
  color: var(--text-tertiary);
}

.stat svg {
  color: var(--text-tertiary);
}

.mod-actions {
  display: flex;
  align-items: center;
}

.btn-sm {
  padding: 8px 16px;
  font-size: 0.875rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-state svg {
  color: var(--text-tertiary);
  margin-bottom: 20px;
}

.empty-state h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.empty-state p {
  font-size: 0.9375rem;
  color: var(--text-secondary);
  margin: 0;
}

/* Scrollbar styling */
.results-grid::-webkit-scrollbar {
  width: 8px;
}

.results-grid::-webkit-scrollbar-track {
  background: var(--bg-primary);
  border-radius: 4px;
}

.results-grid::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.results-grid::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
</style>
