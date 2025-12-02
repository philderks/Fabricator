<template>
  <div class="settings-tab">
    <form class="settings-form" @submit.prevent="handleSave">
      <div class="settings-guard" v-if="formDisabled">
        Stop the server before editing configuration.
      </div>
      <fieldset class="settings-fieldset" :disabled="formDisabled">
      <div class="mode-toggle">
        <div>
          <p class="mode-label">{{ modeLabel }}</p>
          <p class="mode-description">{{ modeDescription }}</p>
        </div>
        <button
          type="button"
          class="mode-button"
          :class="{ active: showAdvanced }"
          @click="toggleMode"
        >
          {{ modeButtonLabel }}
        </button>
      </div>

      <section class="settings-section" data-settings-section="basic">
        <h3 class="section-title">Server Identity</h3>

        <div class="form-row">
          <div class="form-group">
            <label for="server-name">Server Name</label>
            <input
              id="server-name"
              v-model="localSettings.name"
              type="text"
              placeholder="My Minecraft Server"
            >
          </div>
          <div class="form-group">
            <label for="bug-report">Bug Report URL</label>
            <input
              id="bug-report"
              v-model="localSettings.bugReportLink"
              type="url"
              placeholder="https://example.com/issues"
            >
            <span class="form-hint">Shown in support commands</span>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="motd">Message of the Day</label>
            <input
              id="motd"
              v-model="localSettings.motd"
              type="text"
              maxlength="59"
              placeholder="Welcome to Fabricator"
            >
            <span class="form-hint">{{ motdCharacters }}/59 characters</span>
          </div>
          <div class="form-group">
            <label for="server-port">Server Port</label>
            <input
              id="server-port"
              v-model.number="localSettings.port"
              type="number"
              min="1024"
              max="65535"
            >
            <span class="form-hint">Default 25565</span>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="server-ip">Bind Address (optional)</label>
            <input
              id="server-ip"
              v-model="localSettings.serverIp"
              type="text"
              placeholder="0.0.0.0"
            >
          </div>
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
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Running Version</label>
            <div class="readonly-field">
              <input class="readonly-input" :value="serverVersion" type="text" disabled>
              <span class="readonly-badge">Read-only</span>
            </div>
            <span class="form-hint">Version changes require reinstall</span>
          </div>
          <div class="form-group">
            <label>Mod Loader</label>
            <div class="readonly-field">
              <input class="readonly-input" :value="serverLoader" type="text" disabled>
              <span class="readonly-badge">Read-only</span>
            </div>
            <span class="form-hint">Loader changes require reinstall</span>
          </div>
        </div>
      </section>

      <section class="settings-section" data-settings-section="gameplay">
        <h3 class="section-title">Gameplay</h3>

        <div class="form-row">
          <div class="form-group">
            <label for="difficulty">Difficulty</label>
            <select id="difficulty" v-model="localSettings.difficulty">
              <option value="peaceful">Peaceful</option>
              <option value="easy">Easy</option>
              <option value="normal">Normal</option>
              <option value="hard">Hard</option>
            </select>
          </div>
          <div class="form-group">
            <label for="gamemode">Default Gamemode</label>
            <select id="gamemode" v-model="localSettings.gamemode">
              <option value="survival">Survival</option>
              <option value="creative">Creative</option>
              <option value="adventure">Adventure</option>
              <option value="spectator">Spectator</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="spawn-protection">Spawn Protection (blocks)</label>
            <input
              id="spawn-protection"
              v-model.number="localSettings.spawnProtection"
              type="number"
              min="0"
              max="128"
            >
          </div>
          <div class="form-group">
            <label for="idle-timeout">Idle Timeout (minutes)</label>
            <input
              id="idle-timeout"
              v-model.number="localSettings.playerIdleTimeout"
              type="number"
              min="0"
              max="10080"
            >
            <span class="form-hint">0 disables idle kick</span>
          </div>
        </div>

        <div class="form-row" v-if="showAdvanced">
          <div class="form-group">
            <label for="pause-empty">Pause When Empty (seconds)</label>
            <input
              id="pause-empty"
              v-model.number="localSettings.pauseWhenEmptySeconds"
              type="number"
              min="0"
              max="3600"
            >
          </div>
          <div class="form-group">
            <label for="function-level">Function Permission Level</label>
            <input
              id="function-level"
              v-model.number="localSettings.functionPermissionLevel"
              type="number"
              min="1"
              max="4"
            >
          </div>
          <div class="form-group">
            <label for="op-level">Operator Permission Level</label>
            <input
              id="op-level"
              v-model.number="localSettings.opPermissionLevel"
              type="number"
              min="1"
              max="4"
            >
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label" v-if="showAdvanced">
            <input type="checkbox" v-model="localSettings.forceGamemode">
            <span>Force Gamemode</span>
          </label>
          <label class="checkbox-label" v-if="showAdvanced">
            <input type="checkbox" v-model="localSettings.hardcore">
            <span>Hardcore</span>
          </label>
          <label class="checkbox-label" v-if="showAdvanced">
            <input type="checkbox" v-model="localSettings.allowFlight">
            <span>Allow Flight</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.pvp">
            <span>Enable PvP</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.whitelist">
            <span>Enable Whitelist</span>
          </label>
          <label class="checkbox-label" v-if="showAdvanced">
            <input type="checkbox" v-model="localSettings.enforceWhitelist">
            <span>Enforce Whitelist</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.commandBlocks">
            <span>Enable Command Blocks</span>
          </label>
        </div>
      </section>

      <section class="settings-section" data-settings-section="world">
        <h3 class="section-title">World Configuration</h3>

        <div class="warning-notice">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
            <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <div>
            <strong>Warning:</strong>
            Changing level type, seed, or generator settings requires a world reset. Back up first.
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="level-name">World Folder Name</label>
            <input id="level-name" v-model="localSettings.levelName" type="text">
          </div>
          <div class="form-group">
            <label for="level-type">World Type</label>
            <select id="level-type" v-model="localSettings.levelType">
              <option value="default">Default</option>
              <option value="flat">Flat</option>
              <option value="large_biomes">Large Biomes</option>
              <option value="amplified">Amplified</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="world-seed">Seed</label>
            <input
              id="world-seed"
              v-model="localSettings.seed"
              type="text"
              placeholder="Leave empty for random"
            >
          </div>
          <div class="form-group" v-if="showAdvanced">
            <label for="generator-settings">Generator Settings (JSON)</label>
            <textarea
              id="generator-settings"
              v-model="localSettings.generatorSettings"
              placeholder="{}"
            ></textarea>
          </div>
        </div>

        <div class="form-row" v-if="showAdvanced">
          <div class="form-group">
            <label for="max-world-size">Max World Size</label>
            <input
              id="max-world-size"
              v-model.number="localSettings.maxWorldSize"
              type="number"
              min="1000"
            >
          </div>
          <div class="form-group">
            <label for="entity-range">Entity Broadcast Range (%)</label>
            <input
              id="entity-range"
              v-model.number="localSettings.entityBroadcastRangePercentage"
              type="number"
              min="10"
              max="500"
            >
          </div>
          <div class="form-group">
            <label for="max-neighbor-updates">Max Chained Neighbor Updates</label>
            <input
              id="max-neighbor-updates"
              v-model.number="localSettings.maxChainedNeighborUpdates"
              type="number"
              min="1000"
            >
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

      <section
        v-if="showAdvanced"
        class="settings-section"
        data-settings-section="resources"
      >
        <h3 class="section-title">Resources &amp; Packs</h3>

        <div class="form-row">
          <div class="form-group">
            <label for="resource-pack">Resource Pack URL</label>
            <input
              id="resource-pack"
              v-model="localSettings.resourcePack"
              type="url"
              placeholder="https://example.com/resource.zip"
            >
          </div>
          <div class="form-group">
            <label for="resource-pack-sha">Resource Pack SHA-1</label>
            <input
              id="resource-pack-sha"
              v-model="localSettings.resourcePackSha1"
              type="text"
              placeholder="40 character hash"
            >
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="resource-pack-id">Resource Pack ID</label>
            <input id="resource-pack-id" v-model="localSettings.resourcePackId" type="text">
          </div>
          <div class="form-group">
            <label for="resource-pack-prompt">Resource Pack Prompt</label>
            <input
              id="resource-pack-prompt"
              v-model="localSettings.resourcePackPrompt"
              type="text"
              placeholder="Displayed when joining"
            >
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.requireResourcePack">
            <span>Require Players to Accept Pack</span>
          </label>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="enabled-packs">Enabled Data Packs</label>
            <textarea
              id="enabled-packs"
              v-model="localSettings.initialEnabledPacks"
              placeholder="vanilla"
            ></textarea>
            <span class="form-hint">Comma separated identifiers</span>
          </div>
          <div class="form-group">
            <label for="disabled-packs">Disabled Data Packs</label>
            <textarea id="disabled-packs" v-model="localSettings.initialDisabledPacks"></textarea>
          </div>
        </div>
      </section>

      <section
        v-if="showAdvanced"
        class="settings-section"
        data-settings-section="network"
      >
        <h3 class="section-title">Networking &amp; Connectivity</h3>

        <div class="form-row">
          <div class="form-group">
            <label class="toggle-label" for="status-interval">Server Status Broadcast</label>
            <label class="checkbox-label inline">
              <input type="checkbox" v-model="localSettings.enableStatus">
              <span>Enable Status</span>
            </label>
            <input
              id="status-interval"
              v-model.number="localSettings.statusHeartbeatInterval"
              type="number"
              min="0"
              :disabled="statusIntervalDisabled"
            >
            <span class="form-hint">Seconds between status heartbeats</span>
          </div>
          <div class="form-group">
            <label for="rate-limit">Rate Limit (packets/second)</label>
            <input id="rate-limit" v-model.number="localSettings.rateLimit" type="number" min="0">
          </div>
          <div class="form-group">
            <label for="compression-threshold">Compression Threshold (bytes)</label>
            <input
              id="compression-threshold"
              v-model.number="localSettings.networkCompressionThreshold"
              type="number"
              min="-1"
            >
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <div class="label-stack">
              <label for="query-port">Query Port</label>
              <label class="checkbox-label inline">
                <input type="checkbox" v-model="localSettings.enableQuery">
                <span>Enable Query</span>
              </label>
            </div>
            <input
              id="query-port"
              v-model.number="localSettings.queryPort"
              type="number"
              min="1"
              max="65535"
              :disabled="queryDisabled"
            >
          </div>
          <div class="form-group">
            <div class="label-stack">
              <label for="rcon-port">RCON Port</label>
              <label class="checkbox-label inline">
                <input type="checkbox" v-model="localSettings.enableRcon">
                <span>Enable RCON</span>
              </label>
            </div>
            <input
              id="rcon-port"
              v-model.number="localSettings.rconPort"
              type="number"
              min="1"
              max="65535"
              :disabled="rconDisabled"
            >
          </div>
          <div class="form-group">
            <label for="rcon-password">RCON Password</label>
            <input id="rcon-password" v-model="localSettings.rconPassword" type="password" :disabled="rconDisabled">
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.onlineMode">
            <span>Online Mode (Mojang Auth)</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.enforceSecureProfile">
            <span>Enforce Secure Profiles</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.hideOnlinePlayers">
            <span>Hide Player Count</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.preventProxyConnections">
            <span>Prevent Proxy Connections</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.logIps">
            <span>Log Player IPs</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.acceptsTransfers">
            <span>Accept Transfers From Proxy</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.useNativeTransport">
            <span>Use Native Transport</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.syncChunkWrites">
            <span>Sync Chunk Writes</span>
          </label>
        </div>
      </section>

      <section class="settings-section" data-settings-section="performance">
        <h3 class="section-title">Performance</h3>

        <div class="info-notice">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
            <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          <div>
            <strong>Heads up:</strong> Memory, distance, or compression changes require a server restart.
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="memory">Memory Allocation (GB)</label>
            <input id="memory" v-model.number="localSettings.memory" type="number" min="1" max="64" step="0.5">
          </div>
          <div class="form-group">
            <label for="view-distance">View Distance (chunks)</label>
            <input id="view-distance" v-model.number="localSettings.viewDistance" type="number" min="3" max="32">
          </div>
          <div class="form-group">
            <label for="simulation-distance">Simulation Distance (chunks)</label>
            <input
              id="simulation-distance"
              v-model.number="localSettings.simulationDistance"
              type="number"
              min="3"
              max="32"
            >
          </div>
        </div>

        <div class="form-row" v-if="showAdvanced">
          <div class="form-group">
            <label for="max-tick-time">Max Tick Time (ms)</label>
            <input id="max-tick-time" v-model.number="localSettings.maxTickTime" type="number" min="1000">
          </div>
          <div class="form-group">
            <label for="region-compression">Region File Compression</label>
            <select id="region-compression" v-model="localSettings.regionFileCompression">
              <option value="deflate">Deflate</option>
              <option value="gzip">Gzip</option>
              <option value="lz4">LZ4</option>
              <option value="zstd">Zstd</option>
            </select>
          </div>
        </div>
      </section>

      <section
        v-if="showAdvanced"
        class="settings-section"
        data-settings-section="advanced"
      >
        <h3 class="section-title">Security &amp; Automation</h3>

        <div class="form-row">
          <div class="form-group toggle-pair">
            <span class="group-label">Broadcast Console to Ops</span>
            <label class="checkbox-label inline">
              <input type="checkbox" v-model="localSettings.broadcastConsoleToOps">
              <span>Enabled</span>
            </label>
          </div>
          <div class="form-group toggle-pair">
            <span class="group-label">Broadcast RCON to Ops</span>
            <label class="checkbox-label inline">
              <input type="checkbox" v-model="localSettings.broadcastRconToOps">
              <span>Enabled</span>
            </label>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="text-filtering-config">Text Filtering Config</label>
            <textarea
              id="text-filtering-config"
              v-model="localSettings.textFilteringConfig"
              placeholder="{}"
            ></textarea>
          </div>
          <div class="form-group">
            <label for="text-filtering-version">Text Filtering Version</label>
            <input
              id="text-filtering-version"
              v-model.number="localSettings.textFilteringVersion"
              type="number"
              min="0"
            >
          </div>
        </div>

        <div class="form-checkboxes">
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.enableCodeOfConduct">
            <span>Enable Code of Conduct</span>
          </label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="localSettings.enableJmxMonitoring">
            <span>Enable JMX Monitoring</span>
          </label>
        </div>
      </section>

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" @click="handleReset">Reset</button>
        <button type="submit" class="btn btn-primary">Save Changes</button>
      </div>
      </fieldset>
    </form>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'

const props = defineProps({
  settings: {
    type: Object,
    required: true
  },
  serverVersion: {
    type: String,
    default: 'Unknown'
  },
  serverLoader: {
    type: String,
    default: 'Unknown'
  },
  canEdit: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['save', 'reset'])

const localSettings = reactive({ ...props.settings })

const showAdvanced = ref(false)

const motdCharacters = computed(() => localSettings.motd?.length ?? 0)
const statusIntervalDisabled = computed(() => !localSettings.enableStatus)
const queryDisabled = computed(() => !localSettings.enableQuery)
const rconDisabled = computed(() => !localSettings.enableRcon)
const formDisabled = computed(() => !props.canEdit)

const modeLabel = computed(() => (showAdvanced.value ? 'Expert mode' : 'Basic mode'))
const modeDescription = computed(() =>
  showAdvanced.value
    ? 'All configuration options are visible. Handle with care.'
    : 'Hides risky server.properties for quick edits.'
)
const modeButtonLabel = computed(() => (showAdvanced.value ? 'Switch to Basic' : 'Enable Expert Mode'))

const syncFromProps = (value) => {
  if (!value) {
    return
  }
  Object.assign(localSettings, value)
}

watch(
  () => props.settings,
  (value) => {
    syncFromProps(value)
  },
  { deep: true }
)

const toPlainObject = () => JSON.parse(JSON.stringify(localSettings))

const handleSave = () => {
  if (formDisabled.value) {
    return
  }
  emit('save', toPlainObject())
}

const handleReset = () => {
  if (formDisabled.value) {
    return
  }
  emit('reset')
  syncFromProps(props.settings)
}

const toggleMode = () => {
  showAdvanced.value = !showAdvanced.value
}

const enableAdvanced = async () => {
  if (!showAdvanced.value) {
    showAdvanced.value = true
    await nextTick()
  }
}

defineExpose({ enableAdvanced })
</script>

<style scoped>
.settings-fieldset {
  border: none;
  padding: 0;
  margin: 0;
  min-inline-size: 0;
}

.settings-fieldset[disabled] {
  opacity: 0.6;
}

.settings-guard {
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--warning);
  border-radius: 8px;
  color: var(--warning);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
}
</style>
