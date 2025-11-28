<template>
  <BaseModal 
    :show="show" 
    title="Create New Server" 
    size="large"
    @close="handleClose"
  >
    <form @submit.prevent="handleSave" class="settings-form">
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
</template>

<script>
import BaseModal from './BaseModal.vue'
import { createServer, installServer, getFabricGameVersions } from '../../api/servers'
import { useToast } from '../../composables/useToast'

export default {
  name: 'ServerCreateModal',
  components: {
    BaseModal
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
      gameVersions: [],
      loaderOptions: [
        { value: 'fabric', label: 'Fabric (supported)' }
      ],
      formData: {
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
      } catch (error) {
        console.error('Failed to load Fabric game versions:', error)
        this.toast.error('Could not load Minecraft versions.', 'Version Fetch Failed')
      } finally {
        this.versionsLoading = false
      }
    },
    
    async handleCreate() {
      // Validate EULA acceptance
      if (!this.formData.acceptEula) {
        this.toast.warning('You must accept the Minecraft EULA to create a server.', 'EULA Required')
        return
      }

      this.creating = true
      
      try {
        // Create server via API
        const server = await createServer(this.formData)
        this.toast.info('Installing server...', 'Installation')
        const installResult = await installServer(server.id)

        if (installResult.success) {
          this.$emit('create', installResult.server || server)
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
        simulationDistance: 10,
        onlineMode: true,
        whitelist: false,
        pvp: true,
        commandBlocks: true,
        motd: 'A Minecraft Server',
        acceptEula: false
      }
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
