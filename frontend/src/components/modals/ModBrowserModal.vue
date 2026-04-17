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
        <select :value="selectedLoader" disabled>
          <option :value="selectedLoader">{{ loaderLabel }}</option>
        </select>
        
        <select v-model="selectedVersion" @change="performSearch">
          <option value="">All Versions</option>
          <option :value="mcVersion" v-if="mcVersion">{{ mcVersion }} (Server)</option>
          <option
            v-for="version in availableVersionOptions"
            :key="version"
            :value="version"
          >
            {{ version }}
          </option>
        </select>

        <select v-model="sortBy" @change="performSearch">
          <option value="relevance">Relevance</option>
          <option value="downloads">Downloads</option>
          <option value="updated">Updated</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      <div v-if="versionMismatch" class="version-warning">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" />
          <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <span>
          Search filters target <strong>{{ selectedVersion }}</strong>, but your server runs <strong>{{ mcVersion }}</strong>.
          Installs use the server version unless it is unavailable, in which case you can choose another version during installation.
        </span>
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
                <path d="M10 3V13M10 13L6 9M10 13L14 9M4 17H16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              {{ formatNumber(mod.downloads) }}
            </span>
            <span class="stat" v-if="hasVersionInfo(mod)">
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              {{ formatVersions(getVersionList(mod), selectedVersion || mcVersion) }}
            </span>
            <span class="stat category-tag" v-if="mod.categories && mod.categories.length">
              {{ mod.categories[0] }}
            </span>
            <span class="stat category-tag" v-else-if="mod.loaders && mod.loaders.length">
              {{ mod.loaders[0] }}
            </span>
          </div>
        </div>
        <div class="mod-actions">
          <button
            class="btn btn-sm"
            :class="getInstallButtonClass(mod)"
            @click.stop="installMod(mod)"
            :title="getInstallButtonTitle(mod)"
          >
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

  <CompatibilityConfirmModal
    :show="showCompatibilityModal"
    :mod-title="pendingMod ? pendingMod.title : ''"
    :server-version="mcVersion"
    :status="pendingCompatibilityStatus"
    :versions="pendingCompatibilityVersions"
    :initial-selected-version="selectedVersion || mcVersion"
    @confirm="confirmCompatibilityInstall"
    @cancel="cancelCompatibilityInstall"
    @close="cancelCompatibilityInstall"
  />
</template>

<script>
import BaseModal from './BaseModal.vue'
import CompatibilityConfirmModal from './CompatibilityConfirmModal.vue'
import { searchMods, getGameVersions, getModVersions } from '../../api/modrinth'

export default {
  name: 'ModBrowserModal',
  components: {
    BaseModal,
    CompatibilityConfirmModal
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
      selectedLoader: (this.loader || 'fabric').toLowerCase(),
      selectedVersion: this.mcVersion || '',
      sortBy: 'relevance',
      results: [],
      loading: false,
      debounceTimeout: null,
      availableVersions: [],
      pendingMod: null,
      pendingCompatibilityStatus: 'unknown',
      showCompatibilityModal: false,
      pendingCompatibilityVersions: [],
      modVersionCache: {}
    };
  },
  computed: {
    versionMismatch() {
      return Boolean(
        this.selectedVersion &&
        this.mcVersion &&
        this.selectedVersion !== this.mcVersion
      )
    },
    availableVersionOptions() {
      const versions = this.availableVersions || []
      if (!versions.length) {
        return []
      }
      if (!this.mcVersion) {
        return versions
      }
      return versions.filter((version) => version !== this.mcVersion)
    },
    loaderLabel() {
      if (!this.selectedLoader) {
        return 'Any Loader'
      }
      return this.selectedLoader.charAt(0).toUpperCase() + this.selectedLoader.slice(1)
    }
  },
  methods: {
    async loadVersions() {
      try {
        const versions = await getGameVersions()
        const normalized = (versions || [])
          .map((entry) => {
            if (!entry) {
              return null
            }
            if (typeof entry === 'string') {
              return entry
            }
            return entry.version || entry.name || entry.version_number || null
          })
          .filter(Boolean)

        const unique = Array.from(new Set(normalized))
        unique.sort((a, b) => {
          const partsA = a.split('.').map((n) => parseInt(n, 10) || 0)
          const partsB = b.split('.').map((n) => parseInt(n, 10) || 0)
          for (let i = 0; i < Math.max(partsA.length, partsB.length); i += 1) {
            const diff = (partsB[i] || 0) - (partsA[i] || 0)
            if (diff !== 0) {
              return diff
            }
          }
          return 0
        })

        const stableVersionPattern = /^\d+(\.\d+){1,2}$/
        const minVersion = [1, 8, 9]

        const stableVersions = unique.filter((version) => {
          if (!stableVersionPattern.test(version)) {
            return false
          }
          const parts = version.split('.').map((n) => parseInt(n, 10) || 0)
          while (parts.length < 3) {
            parts.push(0)
          }
          for (let i = 0; i < minVersion.length; i += 1) {
            if ((parts[i] || 0) > minVersion[i]) {
              return true
            }
            if ((parts[i] || 0) < minVersion[i]) {
              return false
            }
          }
          return true
        })

        this.availableVersions = stableVersions
      } catch (error) {
        console.error('Failed to load game versions:', error)
        this.availableVersions = []
      }
    },

    async loadCompatibilityVersions(mod) {
      const modId = mod?.project_id
      if (!modId) {
        return []
      }

      const cacheKey = `${modId}:${this.selectedLoader || 'any'}`
      if (this.modVersionCache[cacheKey]) {
        return this.modVersionCache[cacheKey]
      }

      try {
        const filters = {}
        if (this.selectedLoader) {
          filters.loaders = [this.selectedLoader]
        }
        const response = await getModVersions(modId, filters)
        const collected = new Set()

        response.forEach((entry) => {
          if (Array.isArray(entry.game_versions)) {
            entry.game_versions.forEach((version) => {
              if (version) {
                collected.add(version)
              }
            })
          }
        })

        const normalized = Array.from(collected)
        normalized.sort((a, b) => {
          const partsA = a.split('.').map((n) => parseInt(n, 10) || 0)
          const partsB = b.split('.').map((n) => parseInt(n, 10) || 0)
          for (let i = 0; i < Math.max(partsA.length, partsB.length); i += 1) {
            const diff = (partsB[i] || 0) - (partsA[i] || 0)
            if (diff !== 0) {
              return diff
            }
          }
          return 0
        })

        this.modVersionCache[cacheKey] = normalized
        return normalized
      } catch (error) {
        console.error('Failed to load compatibility versions:', error)
        return []
      }
    },

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

        const hits = data.hits || []
        this.results = hits.filter((mod) => this.modSupportsLoader(mod, this.selectedLoader))
      } catch (error) {
        console.error('Search failed:', error)
        this.results = []
      } finally {
        this.loading = false
      }
    },

    async installMod(mod) {
      const status = this.getCompatibilityStatus(mod)

      if (status !== 'full') {
        const versions = await this.loadCompatibilityVersions(mod)
        this.pendingMod = mod
        this.pendingCompatibilityStatus = status
        this.pendingCompatibilityVersions = versions
        this.showCompatibilityModal = true
        return
      }

      this.performInstall(mod)
    },

    performInstall(mod, versionOverride = null) {
      const preferredVersion = versionOverride || this.mcVersion
      this.$emit('install', {
        modId: mod.project_id,
        modTitle: mod.title,
        mcVersion: preferredVersion,
        loader: (this.loader || 'fabric').toLowerCase()
      })
    },

    confirmCompatibilityInstall(selectedVersion = null) {
      if (!this.pendingMod) {
        this.cancelCompatibilityInstall()
        return
      }

      this.performInstall(this.pendingMod, selectedVersion)
      this.pendingMod = null
      this.pendingCompatibilityVersions = []
      this.pendingCompatibilityStatus = 'unknown'
      this.showCompatibilityModal = false
    },

    cancelCompatibilityInstall() {
      this.pendingMod = null
      this.pendingCompatibilityVersions = []
      this.pendingCompatibilityStatus = 'unknown'
      this.showCompatibilityModal = false
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
    },

    formatVersions(versions, highlightVersion = null) {
      if (!versions || !versions.length) return 'N/A'

      const sorted = [...versions].sort((a, b) => {
        const partsA = a.split('.').map((n) => parseInt(n, 10) || 0)
        const partsB = b.split('.').map((n) => parseInt(n, 10) || 0)
        for (let i = 0; i < Math.max(partsA.length, partsB.length); i += 1) {
          const diff = (partsB[i] || 0) - (partsA[i] || 0)
          if (diff !== 0) return diff
        }
        return 0
      })

      if (highlightVersion && versions.includes(highlightVersion)) {
        const others = sorted.length - 1
        if (others === 0) return highlightVersion
        return `${highlightVersion} (+${others} more)`
      }

      if (sorted.length === 1) return sorted[0]
      if (sorted.length === 2) return `${sorted[0]}, ${sorted[1]}`
      return `${sorted[0]} (+${sorted.length - 1} more)`
    },

    getCompatibilityStatus(mod) {
      const versions = this.getVersionList(mod)
      const serverVersion = this.mcVersion

      if (!versions.length || !serverVersion) return 'unknown'
      if (versions.includes(serverVersion)) return 'full'

      const [sMajor, sMinor] = serverVersion.split('.')
      const hasCloseMatch = versions.some((version) => {
        const [vMajor, vMinor] = version.split('.')
        return vMajor === sMajor && vMinor === sMinor
      })

      return hasCloseMatch ? 'likely' : 'unlikely'
    },

    getInstallButtonClass(mod) {
      const status = this.getCompatibilityStatus(mod)
      return {
        'btn-primary': status === 'full',
        'btn-warning': status === 'likely',
        'btn-danger': status === 'unlikely' || status === 'unknown'
      }
    },

    getInstallButtonTitle(mod) {
      const status = this.getCompatibilityStatus(mod)
      switch (status) {
        case 'full':
          return 'Fully compatible'
        case 'likely':
          return 'Likely compatible (similar version)'
        case 'unlikely':
          return 'Possibly incompatible'
        default:
          return 'Compatibility unknown'
      }
    },

    getVersionList(mod) {
      if (mod.game_versions && mod.game_versions.length) {
        return mod.game_versions
      }
      if (mod.version_numbers && mod.version_numbers.length) {
        return mod.version_numbers
      }
      if (mod.versions && mod.versions.length) {
        return mod.versions
      }
      return []
    },

    hasVersionInfo(mod) {
      const versions = this.getVersionList(mod)
      return Array.isArray(versions) && versions.length > 0
    },

    modSupportsLoader(mod, loader) {
      if (!loader) {
        return true
      }
      const loaders = mod.loaders || []
      if (!Array.isArray(loaders) || loaders.length === 0) {
        return true
      }
      return loaders.map((entry) => (entry || '').toLowerCase()).includes(loader.toLowerCase())
    }
  },
  created() {
    this.loadVersions()
  },
  watch: {
    show(newVal) {
      if (!newVal) {
        // Reset on close
        this.searchQuery = '';
        this.results = [];
        this.cancelCompatibilityInstall()
      }

      this.selectedLoader = (this.loader || 'fabric').toLowerCase()
      this.selectedVersion = this.mcVersion || ''

      if (newVal && !this.availableVersions.length) {
        this.loadVersions()
      }
    },
    mcVersion(newVal) {
      this.selectedVersion = newVal || ''
    },
    loader(newVal) {
      this.selectedLoader = (newVal || 'fabric').toLowerCase()
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

.version-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-top: 12px;
  background: color-mix(in oklch, var(--warning) 15%, transparent);
  border: 1px solid color-mix(in oklch, var(--warning) 40%, transparent);
  border-radius: 8px;
  font-size: 0.8125rem;
  color: var(--warning);
}

.version-warning svg {
  flex-shrink: 0;
}

.version-warning strong {
  font-weight: 600;
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

.category-tag {
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 0.75rem;
  text-transform: capitalize;
}

.mod-actions {
  display: flex;
  align-items: center;
}

.btn-sm {
  padding: 8px 16px;
  font-size: 0.875rem;
}

.btn-warning {
  background: var(--warning);
  color: #000;
}

.btn-warning:hover {
  background: color-mix(in oklch, var(--warning) 85%, #000);
}

.btn-danger {
  background: var(--danger);
  color: #fff;
}

.btn-danger:hover {
  background: color-mix(in oklch, var(--danger) 85%, #000);
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
