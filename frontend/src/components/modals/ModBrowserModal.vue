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

        <select v-model="sortBy" @change="performSearch">
          <option value="relevance">Relevance</option>
          <option value="downloads">Downloads</option>
          <option value="updated">Updated</option>
          <option value="newest">Newest</option>
        </select>

        <button
          type="button"
          class="filter-version-toggle"
          @click="toggleVersionFilter"
        >
          {{ versionFilterExpanded ? 'Hide version filter' : 'Version filter' }}
        </button>
      </div>

      <div v-if="versionFilterExpanded" class="filters filters--extra">
        <select v-model="selectedVersion" class="filters__version-select" @change="performSearch">
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
      <SearchResultCard
        v-for="mod in results"
        :key="mod.project_id"
        :icon-url="mod.icon_url"
        :title="mod.title"
        :description="truncate(mod.description, 100)"
        :meta="formatModMeta(mod)"
        @click="selectMod(mod)"
      >
        <AppButton
          :variant="isModInstalled(mod) ? 'ghost' : getInstallButtonVariant(mod)"
          size="sm"
          :disabled="isModInstalled(mod)"
          :title="isModInstalled(mod) ? 'This mod is already in your mods folder' : getInstallButtonTitle(mod)"
          @click.stop="installMod(mod)"
        >
          {{ isModInstalled(mod) ? 'Installed' : 'Install' }}
        </AppButton>
      </SearchResultCard>
    </div>

    <!-- Empty State: no results -->
    <div v-else-if="!loading && searchQuery" class="mod-browser-empty">
      <svg class="mod-browser-empty__icon" width="64" height="64" viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2"/>
        <path d="M21 21L16.5 16.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        <path d="M11 8V14M8 11H14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3 class="mod-browser-empty__heading">No mods found</h3>
      <p class="mod-browser-empty__body">Try adjusting your search or filters</p>
    </div>

    <!-- Initial State -->
    <div v-else class="mod-browser-empty">
      <svg class="mod-browser-empty__icon" width="64" height="64" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M9 9H15M9 13H13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3 class="mod-browser-empty__heading">Search for mods</h3>
      <p class="mod-browser-empty__body">Start typing to find mods for your server</p>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" @click="$emit('close')">Close</AppButton>
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

  <ModDependencyModal
    :show="showDependencyModal"
    :main-mod-title="pendingDependencyModTitle"
    :missing-deps="pendingMissingDeps"
    @cancel="cancelDependencyInstall"
    @install-main-only="onDependencyInstallMainOnly"
    @install-with-deps="onDependencyInstallWithDeps"
  />
</template>

<script>
import BaseModal from './BaseModal.vue'
import CompatibilityConfirmModal from './CompatibilityConfirmModal.vue'
import ModDependencyModal from './ModDependencyModal.vue'
import SearchResultCard from '../ui/SearchResultCard.vue'
import AppButton from '../ui/AppButton.vue'
import {
  searchMods,
  getGameVersions,
  getModVersions,
  resolveProjectVersion,
  getModDetails
} from '../../api/modrinth'
import { useServerStore } from '../../stores/server'
import { installedJarMatchesBrowseHit, installedJarMatchesProjectRef } from '../../utils/modrinthJarMatch'
import { formatNumber, truncate } from '../../utils/format'

export default {
  name: 'ModBrowserModal',
  components: {
    BaseModal,
    CompatibilityConfirmModal,
    ModDependencyModal,
    SearchResultCard,
    AppButton
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
      modVersionCache: {},
      versionFilterExpanded: false,
      showDependencyModal: false,
      pendingDependencyContext: null,
      loadVersionsInflight: false
    };
  },
  computed: {
    pendingDependencyModTitle() {
      return this.pendingDependencyContext?.mod?.title || ''
    },
    pendingMissingDeps() {
      return this.pendingDependencyContext?.missing || []
    },
    effectiveSearchVersion() {
      if (!this.versionFilterExpanded) {
        return this.mcVersion || ''
      }
      return this.selectedVersion
    },
    versionMismatch() {
      if (!this.versionFilterExpanded) {
        return false
      }
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
    isModInstalled(mod) {
      const store = useServerStore()
      return store.installedMods.some((file) =>
        installedJarMatchesBrowseHit(file.filename || file.name, mod)
      )
    },
    toggleVersionFilter() {
      this.versionFilterExpanded = !this.versionFilterExpanded
      if (!this.versionFilterExpanded) {
        this.selectedVersion = this.mcVersion || ''
        if (this.searchQuery.trim()) {
          this.performSearch()
        }
      }
    },
    async loadVersions() {
      // Dedup guard — protects against concurrent calls (e.g. created() hook
      // + open + loader-change races) without affecting any user-visible
      // spinner state.
      if (this.loadVersionsInflight) return
      this.loadVersionsInflight = true
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
      } finally {
        this.loadVersionsInflight = false
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
          version: this.effectiveSearchVersion,
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
      if (this.isModInstalled(mod)) {
        return
      }
      const status = this.getCompatibilityStatus(mod)

      if (status !== 'full') {
        const versions = await this.loadCompatibilityVersions(mod)
        this.pendingMod = mod
        this.pendingCompatibilityStatus = status
        this.pendingCompatibilityVersions = versions
        this.showCompatibilityModal = true
        return
      }

      await this.prepareInstall(mod)
    },

    /** Resolves the Modrinth version used for install and warns when required dependencies are missing. */
    async prepareInstall(mod, versionOverride = null) {
      const preferredVersion = versionOverride || this.mcVersion
      const loader = (this.loader || 'fabric').toLowerCase()
      try {
        const resolved = await resolveProjectVersion(mod.project_id, {
          mc_version: preferredVersion,
          loader
        })
        const version = resolved?.version
        if (!version || !Array.isArray(version.dependencies)) {
          this.performInstall(mod, versionOverride)
          return
        }

        const required = version.dependencies.filter(
          (d) => d && d.dependency_type === 'required' && d.project_id
        )
        const store = useServerStore()
        const missingMap = new Map()
        for (const dep of required) {
          const pid = dep.project_id
          let details
          try {
            details = await getModDetails(pid)
          } catch {
            details = { id: pid, slug: pid, title: pid }
          }
          const ref = {
            id: details.id || pid,
            slug: details.slug
          }
          const installed = store.installedMods.some((file) =>
            installedJarMatchesProjectRef(file.filename || file.name, ref)
          )
          if (!installed) {
            const key = details.id || pid
            if (!missingMap.has(key)) {
              missingMap.set(key, {
                modId: details.id || pid,
                modTitle: details.title || details.slug || String(pid)
              })
            }
          }
        }
        const missing = [...missingMap.values()]
        if (missing.length > 0) {
          this.pendingDependencyContext = { mod, mcVersion: preferredVersion, missing }
          this.showDependencyModal = true
          return
        }
      } catch (e) {
        console.warn('Dependency check skipped:', e)
      }
      this.performInstall(mod, versionOverride)
    },

    performInstall(mod, versionOverride = null, prerequisiteMods = null) {
      const preferredVersion = versionOverride || this.mcVersion
      const payload = {
        modId: mod.project_id,
        modTitle: mod.title,
        mcVersion: preferredVersion,
        loader: (this.loader || 'fabric').toLowerCase()
      }
      if (Array.isArray(prerequisiteMods) && prerequisiteMods.length > 0) {
        payload.prerequisiteMods = prerequisiteMods
      }
      this.$emit('install', payload)
    },

    async confirmCompatibilityInstall(selectedVersion = null) {
      if (!this.pendingMod) {
        this.cancelCompatibilityInstall()
        return
      }

      const mod = this.pendingMod
      this.pendingMod = null
      this.pendingCompatibilityVersions = []
      this.pendingCompatibilityStatus = 'unknown'
      this.showCompatibilityModal = false
      await this.prepareInstall(mod, selectedVersion)
    },

    cancelCompatibilityInstall() {
      this.pendingMod = null
      this.pendingCompatibilityVersions = []
      this.pendingCompatibilityStatus = 'unknown'
      this.showCompatibilityModal = false
    },

    cancelDependencyInstall() {
      this.showDependencyModal = false
      this.pendingDependencyContext = null
    },

    onDependencyInstallMainOnly() {
      const ctx = this.pendingDependencyContext
      this.cancelDependencyInstall()
      if (!ctx?.mod) return
      this.performInstall(ctx.mod, ctx.mcVersion)
    },

    onDependencyInstallWithDeps() {
      const ctx = this.pendingDependencyContext
      this.cancelDependencyInstall()
      if (!ctx?.mod) return
      this.performInstall(ctx.mod, ctx.mcVersion, ctx.missing)
    },

    selectMod(_mod) {
      // Future: Open mod details view
    },

    truncate,

    formatNumber,

    formatModMeta(mod) {
      const parts = []
      if (mod.downloads) parts.push(`${formatNumber(mod.downloads)} downloads`)
      if (mod.categories && mod.categories.length) {
        parts.push(mod.categories[0])
      } else if (mod.loaders && mod.loaders.length) {
        parts.push(mod.loaders[0])
      }
      return parts.join(' · ')
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

    getInstallButtonVariant(mod) {
      const status = this.getCompatibilityStatus(mod)
      if (status === 'full') return 'primary'
      if (status === 'likely') return 'warning'
      return 'danger'
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
        this.versionFilterExpanded = false;
        this.modVersionCache = {};
        this.cancelCompatibilityInstall()
        this.cancelDependencyInstall()
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
      // Parent loader change invalidates per-loader compat cache entries.
      this.modVersionCache = {}
    }
  }
}
</script>

<style scoped>
.search-section {
  margin-bottom: var(--space-6);
}

.search-bar {
  position: relative;
  margin-bottom: var(--space-4);
}

.search-icon {
  position: absolute;
  left: var(--space-4);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.search-bar input {
  width: 100%;
  padding: var(--space-3) var(--space-4) var(--space-3) calc(var(--space-4) + 20px + var(--space-2));
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: border-color 0.15s ease;
}

.search-bar input:focus {
  outline: none;
  border-color: var(--primary);
}

.filters {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.filters--extra {
  margin-top: var(--space-3);
}

.filters--extra .filters__version-select {
  flex: 1 1 100%;
  min-width: 0;
}

.filter-version-toggle {
  flex: 1;
  min-width: 8rem;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.filter-version-toggle:hover {
  border-color: var(--primary);
  color: var(--text-secondary);
}

.filters select {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.filters select:focus {
  outline: none;
  border-color: var(--primary);
}

.version-warning {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  margin-top: var(--space-3);
  background: color-mix(in oklch, var(--warning) 15%, transparent);
  border: 1px solid color-mix(in oklch, var(--warning) 40%, transparent);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--warning);
  line-height: var(--leading-normal);
}

.version-warning svg {
  flex-shrink: 0;
}

.version-warning strong {
  font-weight: 600;
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
  animation: mod-browser-spin 0.8s linear infinite;
}

@keyframes mod-browser-spin {
  to { transform: rotate(360deg); }
}

.results-grid {
  display: grid;
  gap: var(--space-3);
  max-height: 500px;
  overflow-y: auto;
  padding: var(--space-1);
}

/* Scrollbar styling */
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

.mod-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-10) 0;
  color: var(--text-muted);
  text-align: center;
}

.mod-browser-empty__icon {
  color: var(--text-disabled);
}

.mod-browser-empty__heading {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-secondary);
  line-height: var(--leading-tight);
}

.mod-browser-empty__body {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}
</style>
