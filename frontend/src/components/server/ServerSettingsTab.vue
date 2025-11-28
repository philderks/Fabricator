<template>
  <div class="settings-tab">
    <form @submit.prevent="handleSave" class="settings-form">
      <!-- Basic Settings -->
      <section class="settings-section" data-settings-section="basic">
        <h3 class="section-title">Basic Settings</h3>
        
        <div class="form-group">
          <label for="server-name">Server Name</label>
          <input 
            id="server-name"
            v-model="localSettings.name" 
            type="text" 
            placeholder="My Minecraft Server"
          >
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Minecraft Version</label>
            <div class="readonly-field">
              <input 
                :value="serverVersion" 
                type="text"
                disabled
                class="readonly-input"
              >
              <span class="readonly-badge">Read-only</span>
            </div>
            <span class="form-hint warning">Changing version requires server recreation</span>
          </div>

          <div class="form-group">
            <label>Mod Loader</label>
            <div class="readonly-field">
              <input 
                :value="serverLoader" 
                type="text"
                disabled
                class="readonly-input"
              >
              <span class="readonly-badge">Read-only</span>
            </div>
            <span class="form-hint warning">Changing loader requires server recreation</span>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="server-port">Server Port</label>
            <input 
              id="server-port"
              v-model.number="localSettings.port" 
              type="number" 
              min="1024"
              max="65535"
            >
            <span class="form-hint">Default: 25565</span>
          </div>

          <div class="form-group">
            <label for="motd">MOTD</label>
            <input 
              id="motd"
              v-model="localSettings.motd" 
              type="text" 
              maxlength="59"
            >
            <span class="form-hint">{{ localSettings.motd.length }}/59 characters</span>
          </div>
        </div>
      </section>

      <!-- Gameplay Settings -->
      <section class="settings-section" data-settings-section="gameplay">
        <h3 class="section-title">Gameplay</h3>
        
        <div class="form-row">
          <div class="form-group">
            <label for="max-players">Max Players</label>
            <input 
              id="max-players"
              v-model.number="localSettings.maxPlayers" 
              type="number" 
              min="1"
              max="1000"
            >
          </div>

          <div class="form-group">
            <label for="difficulty">Difficulty</label>
            <select id="difficulty" v-model="localSettings.difficulty">
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
            <select id="gamemode" v-model="localSettings.gamemode">
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
              v-model.number="localSettings.viewDistance" 
              type="number" 
              min="3"
              max="32"
            >
            <span class="form-hint">3-32 chunks</span>
          </div>
        </div>
      </section>

      <!-- World Settings -->
      <section class="settings-section" data-settings-section="world">
        <h3 class="section-title">World</h3>
        
        <div class="warning-notice">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
            <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <div>
            <strong>Warning:</strong> Changing world settings (type, seed) will require deleting the existing world. Make a backup first!
          </div>
        </div>
        
        <div class="form-group">
          <label for="level-name">World Name</label>
          <input 
            id="level-name"
            v-model="localSettings.levelName" 
            type="text" 
          >
          <span class="form-hint">Folder name for world files</span>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="level-type">World Type</label>
            <select id="level-type" v-model="localSettings.levelType">
              <option value="default">Default</option>
              <option value="flat">Flat</option>
              <option value="large_biomes">Large Biomes</option>
              <option value="amplified">Amplified</option>
            </select>
            <span class="form-hint warning">Requires world regeneration</span>
          </div>

          <div class="form-group">
            <label for="seed">Seed</label>
            <input 
              id="seed"
              v-model="localSettings.seed" 
              type="text" 
              placeholder="Leave empty for random"
            >
            <span class="form-hint warning">Requires world regeneration</span>
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.generateStructures">
            <span>Generate Structures</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.spawnAnimals">
            <span>Spawn Animals</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.spawnMonsters">
            <span>Spawn Monsters</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.spawnNpcs">
            <span>Spawn NPCs</span>
          </label>
        </div>
      </section>

      <!-- Performance Settings -->
      <section class="settings-section" data-settings-section="performance">
        <h3 class="section-title">Performance</h3>
        
        <div class="info-notice">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <div>
            <strong>Note:</strong> Memory and performance changes require a server restart to take effect.
          </div>
        </div>
        
        <div class="form-row">
          <div class="form-group">
            <label for="memory">Memory Allocation (GB)</label>
            <input 
              id="memory"
              v-model.number="localSettings.memory" 
              type="number" 
              min="1"
              max="32"
              step="0.5"
            >
            <span class="form-hint">Requires server restart</span>
          </div>

          <div class="form-group">
            <label for="simulation-distance">Simulation Distance</label>
            <input 
              id="simulation-distance"
              v-model.number="localSettings.simulationDistance" 
              type="number" 
              min="3"
              max="32"
            >
            <span class="form-hint">Requires server restart</span>
          </div>
        </div>
      </section>

      <!-- Advanced Settings -->
      <section class="settings-section" data-settings-section="advanced">
        <h3 class="section-title">Advanced</h3>
        
        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.onlineMode">
            <span>Online Mode (Authentication)</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.whitelist">
            <span>Enable Whitelist</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.pvp">
            <span>Enable PvP</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.commandBlocks">
            <span>Enable Command Blocks</span>
          </label>
        </div>
      </section>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="handleReset">Reset</button>
        <button type="submit" class="btn btn-primary">Save Changes</button>
      </div>
    </form>
  </div>
</template>

<script>
export default {
  name: 'ServerSettingsTab',
  props: {
    settings: {
      type: Object,
      required: true
    },
    serverVersion: {
      type: String,
      required: true
    },
    serverLoader: {
      type: String,
      required: true
    }
  },
  emits: ['save', 'reset'],
  data() {
    return {
      localSettings: { ...this.settings }
    }
  },
  methods: {
    handleSave() {
      this.$emit('save', { ...this.localSettings })
    },
    handleReset() {
      this.$emit('reset')
      this.localSettings = { ...this.settings }
    }
  },
  watch: {
    settings: {
      deep: true,
      handler(newSettings) {
        this.localSettings = { ...newSettings }
      }
    }
  }
}
</script>

<style scoped>
/* Settings-specific styles only */
.settings-tab {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.section-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}

.readonly-field {
  position: relative;
}

.readonly-input {
  background: var(--bg-tertiary) !important;
  cursor: not-allowed !important;
  color: var(--text-muted) !important;
  text-transform: capitalize;
}

.readonly-badge {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: 4px;
  pointer-events: none;
}

@media (max-width: 1024px) {
  .settings-tab {
    padding: 1.5rem;
  }
}

@media (max-width: 768px) {
  .settings-tab {
    padding: 1rem;
  }
}
</style>
