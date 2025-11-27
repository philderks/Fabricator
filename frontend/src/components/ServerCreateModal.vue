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
              required
            >
              <option value="1.21.3">1.21.3</option>
              <option value="1.21.1">1.21.1</option>
              <option value="1.20.4">1.20.4</option>
              <option value="1.20.1">1.20.1</option>
            </select>
          </div>

          <div class="form-group">
            <label for="mod-loader">Mod Loader</label>
            <select 
              id="mod-loader"
              v-model="formData.loader"
              required
            >
              <option value="fabric">Fabric</option>
              <option value="forge">Forge</option>
              <option value="quilt">Quilt</option>
              <option value="vanilla">Vanilla</option>
            </select>
          </div>
        </div>

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
    </form>

    <template #footer>
      <button type="button" class="btn btn-secondary" @click="handleClose" :disabled="creating">
        Cancel
      </button>
      <button type="button" class="btn btn-primary" @click="handleCreate" :disabled="creating">
        <span v-if="creating" class="btn-loading"></span>
        {{ creating ? 'Creating...' : 'Create Server' }}
      </button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue';

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
  data() {
    return {
      creating: false,
      formData: {
        name: '',
        version: '1.21.3',
        loader: 'fabric',
        port: 25565,
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
        motd: 'A Minecraft Server'
      }
    };
  },
  methods: {
    handleClose() {
      if (!this.creating) {
        this.$emit('close');
        this.resetForm();
      }
    },
    
    async handleCreate() {
      this.creating = true;
      
      try {
        // Future: API call to create server
        await new Promise(resolve => setTimeout(resolve, 1500)); // Simulate API call
        
        this.$emit('create', { ...this.formData });
        this.$emit('close');
        this.resetForm();
      } catch (error) {
        console.error('Failed to create server:', error);
        alert('Failed to create server. Please try again.');
      } finally {
        this.creating = false;
      }
    },
    
    resetForm() {
      this.formData = {
        name: '',
        version: '1.21.3',
        loader: 'fabric',
        port: 25565,
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
        motd: 'A Minecraft Server'
      };
    }
  }
}
</script>

<style scoped>
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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
}

.form-hint {
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.form-hint.warning {
  color: var(--warning);
  font-weight: 500;
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

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-checkboxes {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--primary);
}

.checkbox-label span {
  user-select: none;
}

.warning-notice,
.info-notice {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  line-height: 1.5;
  margin-bottom: 1rem;
}

.warning-notice {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: var(--warning);
}

.warning-notice svg {
  color: var(--warning);
  flex-shrink: 0;
  margin-top: 2px;
}

.info-notice {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--primary);
}

.info-notice svg {
  color: var(--primary);
  flex-shrink: 0;
  margin-top: 2px;
}

.warning-notice strong,
.info-notice strong {
  font-weight: 600;
}

.btn-loading {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 8px;
  vertical-align: middle;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }

  .form-checkboxes {
    grid-template-columns: 1fr;
  }
}
</style>
