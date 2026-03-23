<template>
  <BaseModal 
    :show="show" 
    title="Create New Server" 
    size="large"
    @close="handleClose"
  >
    <form @submit.prevent="handleCreate" class="settings-form">
      <!-- Basic Settings -->
      <section class="settings-section">
        <h3 class="section-title">Basic Settings</h3>
        
        <div class="form-group">
          <label for="server-name">Server Name</label>
          <input 
            id="server-name"
            v-model="formData.name" 
            type="text" 
            placeholder="My Minecraft Server"
            required
          >
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="minecraft-version">Minecraft Version</label>
            <select 
              id="minecraft-version"
              v-model="formData.version"
              @change="handleVersionChange"
              :disabled="versionsLoading || !gameVersions.length"
              required
            >
              <option v-if="versionsLoading" disabled value="">Loading versions...</option>
              <option v-else-if="!versionsLoading && !gameVersions.length" disabled value="">
                No versions available
              </option>
              <option 
                v-for="version in gameVersions" 
                :key="version.version"
                :value="version.version"
              >
                {{ version.version }}<template v-if="version.stable"> (stable)</template>
              </option>
            </select>
            <span v-if="requiredJavaText" class="form-hint">{{ requiredJavaText }}</span>
            <span v-if="javaRequirementWarning" class="form-hint warning-hint">{{ javaRequirementWarning }}</span>
          </div>

          <div class="form-group">
            <label for="mod-loader">Mod Loader</label>
            <select 
              id="mod-loader"
              v-model="formData.loader"
              required
            >
              <option 
                v-for="loaderOption in loaderOptions" 
                :key="loaderOption.value"
                :value="loaderOption.value"
              >
                {{ loaderOption.label }}
              </option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="server-port">Server Port</label>
            <input 
              id="server-port"
              v-model.number="formData.port" 
              type="number" 
              min="1024"
              max="65535"
              placeholder="25565"
            >
            <span class="form-hint">Default: 25565</span>
          </div>

          <div class="form-group">
            <label for="install-path">Installation Path</label>
            <input 
              id="install-path"
              v-model="formData.installPath" 
              type="text" 
              placeholder="Leave empty for auto-generated path"
            >
            <span class="form-hint">Where server files will be stored</span>
          </div>
        </div>
      </section>

      <!-- Modpack Setup -->
      <section class="settings-section">
        <h3 class="section-title">Modpack Setup</h3>

        <div class="mode-toggle" role="tablist" aria-label="Server setup mode">
          <button
            type="button"
            class="mode-toggle-btn"
            :class="{ active: formData.setupMode === 'custom' }"
            @click="formData.setupMode = 'custom'"
          >
            Custom Server
          </button>
          <button
            type="button"
            class="mode-toggle-btn"
            :class="{ active: formData.setupMode === 'modpack' }"
            @click="formData.setupMode = 'modpack'"
          >
            Import Modpack
          </button>
        </div>

        <p class="form-hint">
          Use custom mode for manual setup, or choose a Modrinth modpack by link or search.
        </p>

        <div v-if="formData.setupMode === 'modpack'" class="modpack-panel">
          <div class="form-group">
            <label>Import Method</label>
            <div class="inline-choice">
              <label class="choice-pill">
                <input type="radio" v-model="formData.modpackImportMethod" value="link">
                <span>Link</span>
              </label>
              <label class="choice-pill">
                <input type="radio" v-model="formData.modpackImportMethod" value="search">
                <span>Search</span>
              </label>
            </div>
          </div>

          <div v-if="formData.modpackImportMethod === 'link'" class="form-row modpack-input-row">
            <div class="form-group modpack-grow">
              <label for="modpack-link">Modpack URL or Slug</label>
              <input
                id="modpack-link"
                v-model="modpackLinkInput"
                type="text"
                placeholder="https://modrinth.com/modpack/your-pack"
              >
              <span class="form-hint">Supports Modrinth links, slugs, or project IDs.</span>
            </div>
            <div class="form-group modpack-action">
              <label>&nbsp;</label>
              <button
                type="button"
                class="btn btn-secondary"
                @click="resolveModpackByLink"
                :disabled="modpackLookupLoading || !modpackLinkInput.trim()"
              >
                {{ modpackLookupLoading ? 'Resolving...' : 'Resolve' }}
              </button>
            </div>
          </div>

          <div v-else>
            <div class="form-row modpack-input-row">
              <div class="form-group modpack-grow">
                <label for="modpack-search">Search Modpacks</label>
                <input
                  id="modpack-search"
                  v-model="modpackSearchQuery"
                  type="text"
                  placeholder="All of Fabric, Better Minecraft, ..."
                >
              </div>
              <div class="form-group modpack-action">
                <label>&nbsp;</label>
                <button
                  type="button"
                  class="btn btn-secondary"
                  @click="searchForModpacks"
                  :disabled="modpackSearchLoading || !modpackSearchQuery.trim()"
                >
                  {{ modpackSearchLoading ? 'Searching...' : 'Search' }}
                </button>
              </div>
            </div>

            <div v-if="modpackSearchResults.length" class="modpack-results">
              <button
                v-for="pack in modpackSearchResults"
                :key="pack.project_id"
                type="button"
                class="modpack-result"
                :class="{ selected: selectedModpack && selectedModpack.id === pack.project_id }"
                @click="selectModpackFromSearch(pack)"
              >
                <div class="modpack-result-header">
                  <img
                    v-if="pack.icon_url"
                    :src="pack.icon_url"
                    :alt="pack.title"
                    class="modpack-icon"
                  >
                  <div>
                    <strong>{{ pack.title }}</strong>
                    <p>{{ pack.description || 'No description provided.' }}</p>
                  </div>
                </div>
                <span class="modpack-meta">{{ formatNumber(pack.downloads || 0) }} downloads</span>
              </button>
            </div>

            <p v-if="modpackSearchDone && !modpackSearchLoading && !modpackSearchResults.length" class="form-hint">
              No matching modpacks found for this search.
            </p>
          </div>

          <p v-if="modpackError" class="modpack-error">{{ modpackError }}</p>

          <div v-if="selectedModpack" class="modpack-selected">
            <div>
              <p class="selected-label">Selected Modpack</p>
              <strong>{{ selectedModpack.title }}</strong>
              <p>{{ selectedModpack.description || 'No description provided.' }}</p>
            </div>
            <button type="button" class="btn btn-secondary" @click="clearSelectedModpack">
              Clear
            </button>
          </div>

        </div>
      </section>

      <!-- Gameplay Settings -->
      <section class="settings-section">
        <h3 class="section-title">Gameplay</h3>
        
        <div class="form-row">
          <div class="form-group">
            <label for="max-players">Max Players</label>
            <input 
              id="max-players"
              v-model.number="formData.maxPlayers" 
              type="number" 
              min="1"
              max="1000"
              placeholder="20"
            >
          </div>

          <div class="form-group">
            <label for="difficulty">Difficulty</label>
            <select id="difficulty" v-model="formData.difficulty">
              <option value="peaceful">Peaceful</option>
              <option value="easy">Easy</option>
              <option value="normal">Normal</option>
              <option value="hard">Hard</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="gamemode">Default Gamemode</label>
            <select id="gamemode" v-model="formData.gamemode">
              <option value="survival">Survival</option>
              <option value="creative">Creative</option>
              <option value="adventure">Adventure</option>
              <option value="spectator">Spectator</option>
            </select>
          </div>

          <div class="form-group">
            <label for="view-distance">View Distance</label>
            <input 
              id="view-distance"
              v-model.number="formData.viewDistance" 
              type="number" 
              min="3"
              max="32"
              placeholder="10"
            >
            <span class="form-hint">3-32 chunks</span>
          </div>
        </div>
      </section>

      <!-- World Settings -->
      <section class="settings-section">
        <h3 class="section-title">World</h3>
        

        
        <div class="form-group">
          <label for="level-name">World Name</label>
          <input 
            id="level-name"
            v-model="formData.levelName" 
            type="text" 
            placeholder="world"
          >
          <span class="form-hint">Folder name for world files</span>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="level-type">World Type</label>
            <select id="level-type" v-model="formData.levelType">
              <option value="default">Default</option>
              <option value="flat">Flat</option>
              <option value="large_biomes">Large Biomes</option>
              <option value="amplified">Amplified</option>
            </select>
          </div>

          <div class="form-group">
            <label for="seed">Seed</label>
            <input 
              id="seed"
              v-model="formData.seed" 
              type="text" 
              placeholder="Leave empty for random"
            >
          </div>
        </div>

        <div class="form-group">
          <label for="java-path">Java Executable Path (Optional)</label>
          <input
            id="java-path"
            v-model.trim="formData.javaPath"
            @blur="refreshJavaRequirement"
            type="text"
            placeholder="java or /path/to/java"
          >
          <span class="form-hint">Use a specific Java runtime for this server.</span>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.generateStructures">
            <span>Generate Structures</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.spawnAnimals">
            <span>Spawn Animals</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.spawnMonsters">
            <span>Spawn Monsters</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.spawnNpcs">
            <span>Spawn NPCs</span>
          </label>
        </div>
      </section>

      <!-- Advanced Settings -->
      <section class="settings-section">
        <h3 class="section-title">Advanced</h3>
        

        
        <div class="form-row">
          <div class="form-group">
            <label for="memory">Memory Allocation (GB)</label>
            <input 
              id="memory"
              v-model.number="formData.memory" 
              type="number" 
              min="1"
              max="32"
              step="0.5"
              placeholder="4"
            >
          </div>

          <div class="form-group">
            <label for="simulation-distance">Simulation Distance</label>
            <input 
              id="simulation-distance"
              v-model.number="formData.simulationDistance" 
              type="number" 
              min="3"
              max="32"
              placeholder="10"
            >
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.onlineMode">
            <span>Online Mode (Authentication)</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.whitelist">
            <span>Enable Whitelist</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.pvp">
            <span>Enable PvP</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="formData.commandBlocks">
            <span>Enable Command Blocks</span>
          </label>
        </div>

        <div class="form-group">
          <label for="motd">MOTD (Message of the Day)</label>
          <textarea 
            id="motd"
            v-model="formData.motd" 
            rows="2"
            placeholder="A Minecraft Server"
            maxlength="59"
          ></textarea>
          <span class="form-hint">{{ formData.motd.length }}/59 characters</span>
        </div>
      </section>

      <!-- EULA Agreement -->
      <section class="eula-section">
        <div class="eula-box">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M9 12L11 14L15 10M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <div class="eula-content">
            <label class="eula-label">
              <input 
                type="checkbox" 
                v-model="formData.acceptEula"
                required
              >
              <span>
                I agree to the 
                <a href="https://www.minecraft.net/en-us/eula" target="_blank" rel="noopener noreferrer">
                  Minecraft EULA
                </a>
              </span>
            </label>
            <p class="eula-notice">
              By creating a server, you must accept Mojang's End User License Agreement. This is required to run a Minecraft server.
            </p>
          </div>
        </div>
      </section>
    </form>

    <template #footer>
      <button type="button" class="btn btn-secondary" @click="handleClose" :disabled="creating">
        Cancel
      </button>
      <button type="button" class="btn btn-primary" @click="handleCreate" :disabled="creating || !formData.acceptEula">
        <span v-if="creating" class="btn-loading"></span>
        {{ creating ? 'Creating...' : 'Create Server' }}
      </button>
    </template>
  </BaseModal>

  <ModSideDecisionModal
    :show="showUncertainModsModal"
    :mods="uncertainModsReport"
    :loading="creating"
    @confirm="confirmUncertainModsDecision"
    @cancel="cancelUncertainModsDecision"
    @close="cancelUncertainModsDecision"
  />
</template>

<script>
import BaseModal from './BaseModal.vue'
import { createServer, installServer, getFabricGameVersions, getJavaStatus } from '../../api/servers'
import ModSideDecisionModal from './ModSideDecisionModal.vue'
import { getProjectDetails, searchModpacks, installModpack, resolveProjectVersion } from '../../api/modrinth'
import { useToast } from '../../composables/useToast'

export default {
  name: 'ServerCreateModal',
  components: {
    BaseModal,
    ModSideDecisionModal
  },
  props: {
    show: {
      type: Boolean,
      required: true
    }
  },
  emits: ['close', 'create'],
  setup() {
    const toast = useToast()
    return { toast }
  },
  data() {
    return {
      creating: false,
      versionsLoading: false,
      javaRequirementLoading: false,
      modpackLookupLoading: false,
      modpackSearchLoading: false,
      modpackSearchDone: false,
      modpackLinkInput: '',
      modpackSearchQuery: '',
      modpackSearchResults: [],
      modpackError: '',
      selectedModpack: null,
      showUncertainModsModal: false,
      uncertainModsReport: [],
      pendingUncertainModsResolver: null,
      gameVersions: [],
      javaStatus: null,
      javaRequirementWarning: '',
      loaderOptions: [
        { value: 'fabric', label: 'Fabric (supported)' }
      ],
      formData: {
        setupMode: 'custom',
        modpackImportMethod: 'link',
        modpackReference: '',
        name: '',
        version: '',
        loader: 'fabric',
        port: 25565,
        installPath: '',
        maxPlayers: 20,
        difficulty: 'normal',
        gamemode: 'survival',
        viewDistance: 10,
        levelName: 'world',
        levelType: 'default',
        seed: '',
        generateStructures: true,
        spawnAnimals: true,
        spawnMonsters: true,
        spawnNpcs: true,
        memory: 4,
        javaPath: '',
        simulationDistance: 10,
        onlineMode: true,
        whitelist: false,
        pvp: true,
        commandBlocks: true,
        motd: 'A Minecraft Server',
        acceptEula: false
      }
    };
  },
  created() {
    this.loadGameVersions()
  },
  methods: {
    buildServerPayload() {
      return {
        name: this.formData.name,
        version: this.formData.version,
        loader: this.formData.loader,
        port: this.formData.port,
        installPath: this.formData.installPath,
        maxPlayers: this.formData.maxPlayers,
        difficulty: this.formData.difficulty,
        gamemode: this.formData.gamemode,
        viewDistance: this.formData.viewDistance,
        levelName: this.formData.levelName,
        levelType: this.formData.levelType,
        seed: this.formData.seed,
        generateStructures: this.formData.generateStructures,
        spawnAnimals: this.formData.spawnAnimals,
        spawnMonsters: this.formData.spawnMonsters,
        spawnNpcs: this.formData.spawnNpcs,
        memory: this.formData.memory,
        simulationDistance: this.formData.simulationDistance,
        onlineMode: this.formData.onlineMode,
        whitelist: this.formData.whitelist,
        pvp: this.formData.pvp,
        commandBlocks: this.formData.commandBlocks,
        motd: this.formData.motd,
        acceptEula: this.formData.acceptEula
      }
    },

    extractProjectIdOrSlug(input) {
      if (!input) {
        return ''
      }

      const raw = input.trim()
      if (!raw) {
        return ''
      }

      if (!raw.startsWith('http://') && !raw.startsWith('https://')) {
        return raw.replace(/^@/, '')
      }

      try {
        const parsed = new URL(raw)
        const pathParts = parsed.pathname.split('/').filter(Boolean)
        if (!pathParts.length) {
          return ''
        }

        if ((pathParts[0] === 'modpack' || pathParts[0] === 'project') && pathParts[1]) {
          return pathParts[1]
        }

        return pathParts[pathParts.length - 1]
      } catch {
        return ''
      }
    },

    normalizeModpack(project) {
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

    formatNumber(value) {
      return new Intl.NumberFormat().format(value || 0)
    },

    setSelectedModpack(project) {
      const normalized = this.normalizeModpack(project)
      this.selectedModpack = normalized
      this.formData.modpackReference = normalized.slug || normalized.id || ''
      this.modpackError = ''
    },

    clearSelectedModpack() {
      this.selectedModpack = null
      this.formData.modpackReference = ''
    },

    isNotFoundError(error) {
      if (!error) {
        return false
      }
      if (error.status === 404) {
        return true
      }
      const message = String(error.message || '').toLowerCase()
      return message.includes('not found')
    },

    async resolveModpackByLink() {
      const projectRef = this.extractProjectIdOrSlug(this.modpackLinkInput)
      if (!projectRef) {
        this.modpackError = 'Enter a valid Modrinth modpack URL, slug, or project ID.'
        return
      }

      this.modpackLookupLoading = true
      this.modpackError = ''
      try {
        const project = await getProjectDetails(projectRef)
        if (project.project_type !== 'modpack') {
          this.modpackError = 'That project exists, but it is not a modpack.'
          return
        }
        this.setSelectedModpack(project)
      } catch (error) {
        if (this.isNotFoundError(error)) {
          this.modpackError = `No exact modpack found for "${projectRef}". Showing search results instead.`
          this.modpackSearchQuery = projectRef
          await this.searchForModpacks()
        } else {
          this.modpackError = error.message || 'Could not resolve modpack from the provided link.'
        }
      } finally {
        this.modpackLookupLoading = false
      }
    },

    async searchForModpacks() {
      const query = this.modpackSearchQuery.trim()
      if (!query) {
        this.modpackSearchResults = []
        this.modpackSearchDone = false
        return
      }

      this.modpackSearchLoading = true
      this.modpackSearchDone = false
      this.modpackError = ''
      try {
        const response = await searchModpacks({
          query,
          version: this.formData.version,
          loader: this.formData.loader,
          limit: 8
        })
        this.modpackSearchResults = Array.isArray(response.hits) ? response.hits : []
      } catch (error) {
        this.modpackSearchResults = []
        this.modpackError = error.message || 'Failed to search modpacks.'
      } finally {
        this.modpackSearchLoading = false
        this.modpackSearchDone = true
      }
    },

    selectModpackFromSearch(pack) {
      this.setSelectedModpack(pack)
    },

    async validateSelectedModpackCompatibility() {
      if (this.formData.setupMode !== 'modpack' || !this.selectedModpack) {
        return true
      }

      try {
        await resolveProjectVersion(this.selectedModpack.id, {
          mc_version: this.formData.version,
          loader: this.formData.loader
        })
        return true
      } catch (error) {
        const message = error?.message || 'No compatible modpack version found for the selected Minecraft version.'
        this.modpackError = message
        this.toast.error(message, 'Modpack Incompatible')
        return false
      }
    },

    requestUncertainModsDecision(uncertainMods = []) {
      return new Promise((resolve, reject) => {
        this.uncertainModsReport = Array.isArray(uncertainMods) ? uncertainMods : []
        this.showUncertainModsModal = true
        this.pendingUncertainModsResolver = { resolve, reject }
      })
    },

    confirmUncertainModsDecision(overrides) {
      const resolver = this.pendingUncertainModsResolver
      this.pendingUncertainModsResolver = null
      this.showUncertainModsModal = false
      this.uncertainModsReport = []
      if (resolver?.resolve) {
        resolver.resolve(overrides || {})
      }
    },

    cancelUncertainModsDecision() {
      const resolver = this.pendingUncertainModsResolver
      this.pendingUncertainModsResolver = null
      this.showUncertainModsModal = false
      this.uncertainModsReport = []
      if (resolver?.reject) {
        resolver.reject(new Error('Modpack installation canceled. Unknown mod sides were not confirmed.'))
      }
    },

    async installSelectedModpackOnServer(serverId, modSideOverrides = null) {
      return installModpack(this.selectedModpack.id, {
        mc_version: this.formData.version,
        loader: this.formData.loader,
        server_id: serverId,
        mod_side_overrides: modSideOverrides
      })
    },

    handleClose() {
      if (!this.creating) {
        this.$emit('close');
        this.resetForm();
      }
    },
    
    async loadGameVersions() {
      this.versionsLoading = true
      try {
        const versions = await getFabricGameVersions()
        this.gameVersions = Array.isArray(versions) ? versions : []
        const preferred = this.gameVersions.find(v => v.stable)
        const fallback = preferred || this.gameVersions[0]
        const versionExists = this.gameVersions.some(v => v.version === this.formData.version)
        if ((!this.formData.version || !versionExists) && fallback) {
          this.formData.version = fallback.version
        }
        await this.refreshJavaRequirement()
      } catch (error) {
        console.error('Failed to load Fabric game versions:', error)
        this.toast.error('Could not load Minecraft versions.', 'Version Fetch Failed')
      } finally {
        this.versionsLoading = false
      }
    },

    async refreshJavaRequirement() {
      if (!this.formData.version) {
        this.javaStatus = null
        this.javaRequirementWarning = ''
        return
      }

      this.javaRequirementLoading = true
      try {
        this.javaStatus = await getJavaStatus({
          mcVersion: this.formData.version,
          javaPath: this.formData.javaPath || undefined
        })
        this.javaRequirementWarning = this.javaStatus?.compatibility?.warning || ''
      } catch (error) {
        console.error('Failed to resolve Java requirement:', error)
        this.javaRequirementWarning = 'Could not verify Java requirement right now.'
      } finally {
        this.javaRequirementLoading = false
      }
    },

    async handleVersionChange() {
      await this.refreshJavaRequirement()
    },
    
    async handleCreate() {
      if (!this.formData.name.trim()) {
        this.toast.warning('Please enter a server name.', 'Name Required')
        return
      }

      if (!this.formData.version) {
        this.toast.warning('Please select a Minecraft version.', 'Version Required')
        return
      }

      if (!this.formData.acceptEula) {
        this.toast.warning('You must accept the Minecraft EULA to create a server.', 'EULA Required')
        return
      }

      if (this.formData.setupMode === 'modpack' && !this.selectedModpack) {
        this.toast.warning('Choose a modpack by link or search before creating the server.', 'Modpack Required')
        return
      }

      if (this.formData.setupMode === 'modpack') {
        const compatible = await this.validateSelectedModpackCompatibility()
        if (!compatible) {
          return
        }
      }

      this.creating = true
      
      try {
        // Create server via API
        const server = await createServer(this.buildServerPayload())
        this.toast.info('Installing server...', 'Installation')
        const installResult = await installServer(server.id)

        if (installResult.success) {
          const createdServer = installResult.server || server
          let modpackInstallError = null

          if (this.formData.setupMode === 'modpack' && this.selectedModpack) {
            this.toast.info(`Installing ${this.selectedModpack.title}...`, 'Modpack')
            try {
              let installResult = null
              let overrideMap = null
              while (true) {
                try {
                  installResult = await this.installSelectedModpackOnServer(createdServer.id, overrideMap)
                  break
                } catch (installError) {
                  const uncertainMods = installError?.data?.uncertain_mod_files
                  const canContinueWithUncertain = Boolean(installError?.data?.can_continue_with_uncertain)
                  if (
                    installError?.status === 409
                    && canContinueWithUncertain
                    && Array.isArray(uncertainMods)
                    && uncertainMods.length
                  ) {
                    this.toast.warning('Some mods need a server/client decision before install can continue.', 'Uncertain Mod Side')
                    overrideMap = await this.requestUncertainModsDecision(uncertainMods)
                    continue
                  }
                  throw installError
                }
              }

              if (installResult?.uncertain_mod_files?.length) {
                this.toast.info(
                  `${installResult.uncertain_mod_files.length} uncertain mods were classified by your selection.`,
                  'Modpack Choices Applied'
                )
              }
              this.toast.success(`${this.selectedModpack.title} installed successfully!`, 'Modpack Installed')
            } catch (modpackError) {
              modpackInstallError = modpackError?.message || 'Modpack installation failed. You can install it manually from the server dashboard.'
              this.toast.error(
                modpackInstallError,
                'Modpack Failed'
              )
            }
          }

          this.$emit('create', {
            ...createdServer,
            modpackInstallError
          })
          this.$emit('close')
          this.resetForm()
        } else {
          this.toast.error(installResult.message || 'Installation failed', 'Server Installation Failed')
        }
      } catch (error) {
        console.error('Failed to create server:', error)
        this.toast.error(error.message, 'Server Creation Failed')
      } finally {
        this.creating = false
      }
    },
    
    resetForm() {
      const preservedVersion = this.formData.version
      this.formData = {
        setupMode: 'custom',
        modpackImportMethod: 'link',
        modpackReference: '',
        name: '',
        version: preservedVersion || (this.gameVersions[0]?.version || ''),
        loader: 'fabric',
        port: 25565,
        installPath: '',
        maxPlayers: 20,
        difficulty: 'normal',
        gamemode: 'survival',
        viewDistance: 10,
        levelName: 'world',
        levelType: 'default',
        seed: '',
        generateStructures: true,
        spawnAnimals: true,
        spawnMonsters: true,
        spawnNpcs: true,
        memory: 4,
        javaPath: '',
        simulationDistance: 10,
        onlineMode: true,
        whitelist: false,
        pvp: true,
        commandBlocks: true,
        motd: 'A Minecraft Server',
        acceptEula: false
      }
      this.javaStatus = null
      this.javaRequirementWarning = ''

      this.modpackLookupLoading = false
      this.modpackSearchLoading = false
      this.modpackSearchDone = false
      this.modpackLinkInput = ''
      this.modpackSearchQuery = ''
      this.modpackSearchResults = []
      this.modpackError = ''
      this.selectedModpack = null
      this.showUncertainModsModal = false
      this.uncertainModsReport = []
      this.pendingUncertainModsResolver = null
    }
  },
  computed: {
    requiredJavaText() {
      const required = this.javaStatus?.required_java
      if (!required) {
        return ''
      }
      const detected = this.javaStatus?.detected_major
      if (detected && detected < required) {
        return `Requires Java ${required}+ (detected Java ${detected}).`
      }
      return `Requires Java ${required}+`
    }
  }
}
</script>

<style scoped>
/* Modal-specific styles only */
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-color);
}

.warning-hint {
  color: var(--warning, #f59e0b);
}

.mode-toggle {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: color-mix(in oklch, var(--bg-secondary) 88%, transparent);
  gap: 0.25rem;
}

.mode-toggle-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  padding: 0.5rem 0.9rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
}

.mode-toggle-btn.active {
  background: color-mix(in oklch, var(--primary) 15%, transparent);
  color: var(--text-primary);
}

.modpack-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: color-mix(in oklch, var(--bg-tertiary) 75%, transparent);
}

.inline-choice {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.choice-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  padding: 0.4rem 0.75rem;
  cursor: pointer;
  font-size: 0.875rem;
}

.modpack-input-row {
  align-items: end;
}

.modpack-grow {
  flex: 1;
}

.modpack-action {
  min-width: 140px;
}

.modpack-results {
  display: grid;
  gap: 0.75rem;
}

.modpack-result {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 0.75rem;
  background: var(--bg-primary);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.modpack-result:hover {
  border-color: color-mix(in oklch, var(--primary) 35%, var(--border-color));
}

.modpack-result.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--primary) 20%, transparent);
}

.modpack-result-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.modpack-result-header p {
  margin: 0.15rem 0 0;
  color: var(--text-muted);
  font-size: 0.8125rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.modpack-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.modpack-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid var(--border-color);
}

.modpack-error {
  margin: 0;
  color: var(--danger, #d14343);
  font-size: 0.875rem;
}

.modpack-selected {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: start;
  padding: 0.85rem 1rem;
  border-radius: 10px;
  background: color-mix(in oklch, var(--success, #22a06b) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--success, #22a06b) 28%, transparent);
}

.modpack-selected p {
  margin: 0.2rem 0 0;
  color: var(--text-secondary);
  font-size: 0.8125rem;
}

.selected-label {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

@media (max-width: 900px) {
  .modpack-action {
    min-width: 0;
  }

  .modpack-result {
    flex-direction: column;
    align-items: stretch;
  }

  .modpack-meta {
    white-space: normal;
  }

  .modpack-selected {
    flex-direction: column;
  }
}

/* EULA Section */
.eula-section {
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 2px solid var(--border-color);
}

.eula-box {
  display: flex;
  gap: 1rem;
  padding: 1.5rem;
  background: color-mix(in oklch, var(--primary) 5%, transparent);
  border: 2px solid color-mix(in oklch, var(--primary) 20%, transparent);
  border-radius: 12px;
}

.eula-box svg {
  color: var(--primary);
  flex-shrink: 0;
  margin-top: 2px;
}

.eula-content {
  flex: 1;
}

.eula-label {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  font-size: 0.9375rem;
  color: var(--text-primary);
  cursor: pointer;
  margin-bottom: 0.75rem;
}

.eula-label input[type="checkbox"] {
  width: 20px;
  height: 20px;
  margin-top: 2px;
  cursor: pointer;
  accent-color: var(--primary);
  flex-shrink: 0;
}

.eula-label span {
  user-select: none;
  line-height: 1.5;
}

.eula-label a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s;
}

.eula-label a:hover {
  border-bottom-color: var(--primary);
}

.eula-notice {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-muted);
  line-height: 1.5;
  padding-left: 2rem;
}
</style>
