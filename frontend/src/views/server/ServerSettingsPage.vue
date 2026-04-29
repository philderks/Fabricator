<script setup>
import { computed, ref } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const showAdvanced = ref(false)

const motdCharacters = computed(() => store.serverSettings?.motd?.length ?? 0)
const statusIntervalDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableStatus
)
const queryDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableQuery
)
const rconDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableRcon
)

const modeLabel = computed(() => (showAdvanced.value ? 'Expert mode' : 'Basic mode'))
const modeDescription = computed(() =>
  showAdvanced.value
    ? 'All configuration options are visible. Handle with care.'
    : 'Hides risky server.properties for quick edits.'
)
const modeButtonLabel = computed(() =>
  showAdvanced.value ? 'Switch to Basic' : 'Enable Expert Mode'
)

const toggleMode = () => {
  showAdvanced.value = !showAdvanced.value
}

const onSave = () => {
  if (!store.serverSettings || !store.canEditSettings) return
  store.handleSaveSettings(JSON.parse(JSON.stringify(store.serverSettings)))
}

const onReset = () => {
  if (!store.canEditSettings) return
  store.resetSettings()
}
</script>

<template>
  <div class="settings-page" v-if="store.serverSettings">
    <div class="settings-page__guard" v-if="!store.canEditSettings">
      Stop the server before editing configuration.
    </div>

    <Panel title="Mode">
      <div class="settings-page__mode">
        <div>
          <p class="settings-page__mode-label">{{ modeLabel }}</p>
          <p class="settings-page__mode-description">{{ modeDescription }}</p>
        </div>
        <button
          type="button"
          class="settings-page__mode-button"
          :class="{ 'settings-page__mode-button--active': showAdvanced }"
          @click="toggleMode"
        >
          {{ modeButtonLabel }}
        </button>
      </div>
    </Panel>

    <Panel title="Server Identity">
      <div class="settings-page__grid">
        <label class="settings-page__field">
          <span class="settings-page__label">Server Name</span>
          <input
            class="settings-page__input"
            type="text"
            placeholder="My Minecraft Server"
            v-model="store.serverSettings.name"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Bug Report URL</span>
          <input
            class="settings-page__input"
            type="url"
            placeholder="https://example.com/issues"
            v-model="store.serverSettings.bugReportLink"
            :disabled="!store.canEditSettings"
          />
          <span class="settings-page__hint">Shown in support commands</span>
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Message of the Day</span>
          <input
            class="settings-page__input"
            type="text"
            maxlength="59"
            placeholder="Welcome to Fabricator"
            v-model="store.serverSettings.motd"
            :disabled="!store.canEditSettings"
          />
          <span class="settings-page__hint">{{ motdCharacters }}/59 characters</span>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Server Port</span>
          <input
            class="settings-page__input"
            type="number"
            min="1024"
            max="65535"
            v-model.number="store.serverSettings.port"
            :disabled="!store.canEditSettings"
          />
          <span class="settings-page__hint">Default 25565</span>
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Bind Address (optional)</span>
          <input
            class="settings-page__input"
            type="text"
            placeholder="0.0.0.0"
            v-model="store.serverSettings.serverIp"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Max Players</span>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="1000"
            v-model.number="store.serverSettings.maxPlayers"
            :disabled="!store.canEditSettings"
          />
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Running Version</span>
          <div class="settings-page__readonly">
            <input
              class="settings-page__input"
              type="text"
              :value="store.serverStatus.version"
              disabled
            />
            <span class="settings-page__readonly-badge">Read-only</span>
          </div>
          <span class="settings-page__hint">Version changes require reinstall</span>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Mod Loader</span>
          <div class="settings-page__readonly">
            <input
              class="settings-page__input"
              type="text"
              :value="store.serverStatus.loader"
              disabled
            />
            <span class="settings-page__readonly-badge">Read-only</span>
          </div>
          <span class="settings-page__hint">Loader changes require reinstall</span>
        </label>
      </div>
    </Panel>

    <Panel title="Gameplay">
      <div class="settings-page__grid">
        <label class="settings-page__field">
          <span class="settings-page__label">Difficulty</span>
          <select
            class="settings-page__select"
            v-model="store.serverSettings.difficulty"
            :disabled="!store.canEditSettings"
          >
            <option value="peaceful">Peaceful</option>
            <option value="easy">Easy</option>
            <option value="normal">Normal</option>
            <option value="hard">Hard</option>
          </select>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Default Gamemode</span>
          <select
            class="settings-page__select"
            v-model="store.serverSettings.gamemode"
            :disabled="!store.canEditSettings"
          >
            <option value="survival">Survival</option>
            <option value="creative">Creative</option>
            <option value="adventure">Adventure</option>
            <option value="spectator">Spectator</option>
          </select>
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Spawn Protection (blocks)</span>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            max="128"
            v-model.number="store.serverSettings.spawnProtection"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Idle Timeout (minutes)</span>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            max="10080"
            v-model.number="store.serverSettings.playerIdleTimeout"
            :disabled="!store.canEditSettings"
          />
          <span class="settings-page__hint">0 disables idle kick</span>
        </label>

        <template v-if="showAdvanced">
          <label class="settings-page__field">
            <span class="settings-page__label">Pause When Empty (seconds)</span>
            <input
              class="settings-page__input"
              type="number"
              min="0"
              max="3600"
              v-model.number="store.serverSettings.pauseWhenEmptySeconds"
              :disabled="!store.canEditSettings"
            />
          </label>
          <label class="settings-page__field">
            <span class="settings-page__label">Function Permission Level</span>
            <input
              class="settings-page__input"
              type="number"
              min="1"
              max="4"
              v-model.number="store.serverSettings.functionPermissionLevel"
              :disabled="!store.canEditSettings"
            />
          </label>
          <label class="settings-page__field">
            <span class="settings-page__label">Operator Permission Level</span>
            <input
              class="settings-page__input"
              type="number"
              min="1"
              max="4"
              v-model.number="store.serverSettings.opPermissionLevel"
              :disabled="!store.canEditSettings"
            />
          </label>
        </template>
      </div>

      <div class="settings-page__toggles">
        <label
          v-if="showAdvanced"
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.forceGamemode"
            :disabled="!store.canEditSettings"
          />
          <span>Force Gamemode</span>
        </label>
        <label
          v-if="showAdvanced"
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.hardcore"
            :disabled="!store.canEditSettings"
          />
          <span>Hardcore</span>
        </label>
        <label
          v-if="showAdvanced"
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.allowFlight"
            :disabled="!store.canEditSettings"
          />
          <span>Allow Flight</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.pvp"
            :disabled="!store.canEditSettings"
          />
          <span>Enable PvP</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.whitelist"
            :disabled="!store.canEditSettings"
          />
          <span>Enable Whitelist</span>
        </label>
        <label
          v-if="showAdvanced"
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.enforceWhitelist"
            :disabled="!store.canEditSettings"
          />
          <span>Enforce Whitelist</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.commandBlocks"
            :disabled="!store.canEditSettings"
          />
          <span>Enable Command Blocks</span>
        </label>
      </div>
    </Panel>

    <Panel title="World Configuration">
      <div class="settings-page__notice settings-page__notice--warning">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
          <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div>
          <strong>Warning:</strong>
          Changing level type, seed, or generator settings requires a world reset. Back up first.
        </div>
      </div>

      <div class="settings-page__grid">
        <label class="settings-page__field">
          <span class="settings-page__label">World Folder Name</span>
          <input
            class="settings-page__input"
            type="text"
            v-model="store.serverSettings.levelName"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">World Type</span>
          <select
            class="settings-page__select"
            v-model="store.serverSettings.levelType"
            :disabled="!store.canEditSettings"
          >
            <option value="default">Default</option>
            <option value="flat">Flat</option>
            <option value="large_biomes">Large Biomes</option>
            <option value="amplified">Amplified</option>
          </select>
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Seed</span>
          <input
            class="settings-page__input"
            type="text"
            placeholder="Leave empty for random"
            v-model="store.serverSettings.seed"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label v-if="showAdvanced" class="settings-page__field">
          <span class="settings-page__label">Generator Settings (JSON)</span>
          <textarea
            class="settings-page__input settings-page__textarea"
            placeholder="{}"
            v-model="store.serverSettings.generatorSettings"
            :disabled="!store.canEditSettings"
          ></textarea>
        </label>

        <template v-if="showAdvanced">
          <label class="settings-page__field">
            <span class="settings-page__label">Max World Size</span>
            <input
              class="settings-page__input"
              type="number"
              min="1000"
              v-model.number="store.serverSettings.maxWorldSize"
              :disabled="!store.canEditSettings"
            />
          </label>
          <label class="settings-page__field">
            <span class="settings-page__label">Entity Broadcast Range (%)</span>
            <input
              class="settings-page__input"
              type="number"
              min="10"
              max="500"
              v-model.number="store.serverSettings.entityBroadcastRangePercentage"
              :disabled="!store.canEditSettings"
            />
          </label>
          <label class="settings-page__field">
            <span class="settings-page__label">Max Chained Neighbor Updates</span>
            <input
              class="settings-page__input"
              type="number"
              min="1000"
              v-model.number="store.serverSettings.maxChainedNeighborUpdates"
              :disabled="!store.canEditSettings"
            />
          </label>
        </template>
      </div>

      <div class="settings-page__toggles">
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.generateStructures"
            :disabled="!store.canEditSettings"
          />
          <span>Generate Structures</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.spawnAnimals"
            :disabled="!store.canEditSettings"
          />
          <span>Spawn Animals</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.spawnMonsters"
            :disabled="!store.canEditSettings"
          />
          <span>Spawn Monsters</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.spawnNpcs"
            :disabled="!store.canEditSettings"
          />
          <span>Spawn NPCs</span>
        </label>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" title="Resources & Packs">
      <div class="settings-page__grid">
        <label class="settings-page__field">
          <span class="settings-page__label">Resource Pack URL</span>
          <input
            class="settings-page__input"
            type="url"
            placeholder="https://example.com/resource.zip"
            v-model="store.serverSettings.resourcePack"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Resource Pack SHA-1</span>
          <input
            class="settings-page__input"
            type="text"
            placeholder="40 character hash"
            v-model="store.serverSettings.resourcePackSha1"
            :disabled="!store.canEditSettings"
          />
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Resource Pack ID</span>
          <input
            class="settings-page__input"
            type="text"
            v-model="store.serverSettings.resourcePackId"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Resource Pack Prompt</span>
          <input
            class="settings-page__input"
            type="text"
            placeholder="Displayed when joining"
            v-model="store.serverSettings.resourcePackPrompt"
            :disabled="!store.canEditSettings"
          />
        </label>
      </div>

      <div class="settings-page__toggles">
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.requireResourcePack"
            :disabled="!store.canEditSettings"
          />
          <span>Require Players to Accept Pack</span>
        </label>
      </div>

      <div class="settings-page__grid">
        <label class="settings-page__field">
          <span class="settings-page__label">Enabled Data Packs</span>
          <textarea
            class="settings-page__input settings-page__textarea"
            placeholder="vanilla"
            v-model="store.serverSettings.initialEnabledPacks"
            :disabled="!store.canEditSettings"
          ></textarea>
          <span class="settings-page__hint">Comma separated identifiers</span>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Disabled Data Packs</span>
          <textarea
            class="settings-page__input settings-page__textarea"
            v-model="store.serverSettings.initialDisabledPacks"
            :disabled="!store.canEditSettings"
          ></textarea>
        </label>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" title="Networking & Connectivity">
      <div class="settings-page__grid settings-page__grid--three">
        <label class="settings-page__field">
          <span class="settings-page__label">Server Status Broadcast</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableStatus"
              :disabled="!store.canEditSettings"
            />
            <span>Enable Status</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            v-model.number="store.serverSettings.statusHeartbeatInterval"
            :disabled="statusIntervalDisabled"
          />
          <span class="settings-page__hint">Seconds between status heartbeats</span>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Rate Limit (packets/second)</span>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            v-model.number="store.serverSettings.rateLimit"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Compression Threshold (bytes)</span>
          <input
            class="settings-page__input"
            type="number"
            min="-1"
            v-model.number="store.serverSettings.networkCompressionThreshold"
            :disabled="!store.canEditSettings"
          />
        </label>

        <label class="settings-page__field">
          <span class="settings-page__label">Query Port</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableQuery"
              :disabled="!store.canEditSettings"
            />
            <span>Enable Query</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="65535"
            v-model.number="store.serverSettings.queryPort"
            :disabled="queryDisabled"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">RCON Port</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableRcon"
              :disabled="!store.canEditSettings"
            />
            <span>Enable RCON</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="65535"
            v-model.number="store.serverSettings.rconPort"
            :disabled="rconDisabled"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">RCON Password</span>
          <input
            class="settings-page__input"
            type="password"
            v-model="store.serverSettings.rconPassword"
            :disabled="rconDisabled"
          />
        </label>
      </div>

      <div class="settings-page__toggles">
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.onlineMode"
            :disabled="!store.canEditSettings"
          />
          <span>Online Mode (Mojang Auth)</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.enforceSecureProfile"
            :disabled="!store.canEditSettings"
          />
          <span>Enforce Secure Profiles</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.hideOnlinePlayers"
            :disabled="!store.canEditSettings"
          />
          <span>Hide Player Count</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.preventProxyConnections"
            :disabled="!store.canEditSettings"
          />
          <span>Prevent Proxy Connections</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.logIps"
            :disabled="!store.canEditSettings"
          />
          <span>Log Player IPs</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.acceptsTransfers"
            :disabled="!store.canEditSettings"
          />
          <span>Accept Transfers From Proxy</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.useNativeTransport"
            :disabled="!store.canEditSettings"
          />
          <span>Use Native Transport</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.syncChunkWrites"
            :disabled="!store.canEditSettings"
          />
          <span>Sync Chunk Writes</span>
        </label>
      </div>
    </Panel>

    <Panel title="Performance">
      <div class="settings-page__notice settings-page__notice--info">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div>
          <strong>Heads up:</strong> Memory, distance, or compression changes require a server restart.
        </div>
      </div>

      <div class="settings-page__grid settings-page__grid--three">
        <label class="settings-page__field">
          <span class="settings-page__label">Memory Allocation (GB)</span>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="64"
            step="0.5"
            v-model.number="store.serverSettings.memory"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">View Distance (chunks)</span>
          <input
            class="settings-page__input"
            type="number"
            min="3"
            max="32"
            v-model.number="store.serverSettings.viewDistance"
            :disabled="!store.canEditSettings"
          />
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Simulation Distance (chunks)</span>
          <input
            class="settings-page__input"
            type="number"
            min="3"
            max="32"
            v-model.number="store.serverSettings.simulationDistance"
            :disabled="!store.canEditSettings"
          />
        </label>

        <template v-if="showAdvanced">
          <label class="settings-page__field">
            <span class="settings-page__label">Max Tick Time (ms)</span>
            <input
              class="settings-page__input"
              type="number"
              min="1000"
              v-model.number="store.serverSettings.maxTickTime"
              :disabled="!store.canEditSettings"
            />
          </label>
          <label class="settings-page__field">
            <span class="settings-page__label">Region File Compression</span>
            <select
              class="settings-page__select"
              v-model="store.serverSettings.regionFileCompression"
              :disabled="!store.canEditSettings"
            >
              <option value="deflate">Deflate</option>
              <option value="gzip">Gzip</option>
              <option value="lz4">LZ4</option>
              <option value="zstd">Zstd</option>
            </select>
          </label>
        </template>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" title="Security & Automation">
      <div class="settings-page__grid">
        <div class="settings-page__field">
          <span class="settings-page__label">Broadcast Console to Ops</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.broadcastConsoleToOps"
              :disabled="!store.canEditSettings"
            />
            <span>Enabled</span>
          </label>
        </div>
        <div class="settings-page__field">
          <span class="settings-page__label">Broadcast RCON to Ops</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.broadcastRconToOps"
              :disabled="!store.canEditSettings"
            />
            <span>Enabled</span>
          </label>
        </div>

        <label class="settings-page__field">
          <span class="settings-page__label">Text Filtering Config</span>
          <textarea
            class="settings-page__input settings-page__textarea"
            placeholder="{}"
            v-model="store.serverSettings.textFilteringConfig"
            :disabled="!store.canEditSettings"
          ></textarea>
        </label>
        <label class="settings-page__field">
          <span class="settings-page__label">Text Filtering Version</span>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            v-model.number="store.serverSettings.textFilteringVersion"
            :disabled="!store.canEditSettings"
          />
        </label>
      </div>

      <div class="settings-page__toggles">
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.enableCodeOfConduct"
            :disabled="!store.canEditSettings"
          />
          <span>Enable Code of Conduct</span>
        </label>
        <label
          class="settings-page__toggle"
          :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
        >
          <input
            type="checkbox"
            v-model="store.serverSettings.enableJmxMonitoring"
            :disabled="!store.canEditSettings"
          />
          <span>Enable JMX Monitoring</span>
        </label>
      </div>
    </Panel>

    <div class="settings-page__footer">
      <AppButton variant="ghost" @click="onReset" :disabled="!store.canEditSettings">Reset</AppButton>
      <AppButton variant="primary" @click="onSave" :disabled="!store.canEditSettings">Save changes</AppButton>
    </div>

    <Panel title="Danger zone">
      <div class="settings-page__danger">
        <p class="settings-page__danger-text">Deleting a server removes its files and backups. This cannot be undone.</p>
        <AppButton variant="danger" :loading="store.deletingServer" @click="store.openDeleteServerModal">
          {{ store.deletingServer ? 'Deleting…' : 'Delete server' }}
        </AppButton>
      </div>
    </Panel>
  </div>
  <div v-else class="settings-page__loading">Loading settings…</div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 880px;
}

.settings-page__loading {
  color: var(--text-muted);
  font-size: var(--text-sm);
  padding: var(--space-5);
  text-align: center;
}

.settings-page__guard {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  color: var(--warning);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  font-size: var(--text-sm);
}

.settings-page__mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.settings-page__mode-label {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.settings-page__mode-description {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__mode-button {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 12px;
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease;
}

.settings-page__mode-button:hover {
  border-color: var(--primary);
  color: var(--text-primary);
}

.settings-page__mode-button--active {
  border-color: var(--primary);
  color: var(--primary);
}

.settings-page__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}

.settings-page__grid--three {
  grid-template-columns: repeat(3, 1fr);
}

.settings-page__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.settings-page__field--full {
  grid-column: 1 / -1;
}

.settings-page__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.settings-page__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__input,
.settings-page__select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 10px;
  font-family: inherit;
  font-size: var(--text-sm);
  width: 100%;
}

.settings-page__textarea {
  min-height: 72px;
  resize: vertical;
  font-family: var(--font-mono, ui-monospace, monospace);
}

.settings-page__input:focus,
.settings-page__select:focus {
  outline: none;
  border-color: var(--primary);
}

.settings-page__input:disabled,
.settings-page__select:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.settings-page__readonly {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.settings-page__readonly-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  white-space: nowrap;
}

.settings-page__toggles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin-top: var(--space-3);
}

.settings-page__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.settings-page__toggle--inline {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__toggle input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--primary);
  cursor: pointer;
}

.settings-page__toggle--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settings-page__toggle--disabled input[type="checkbox"] {
  cursor: not-allowed;
}

.settings-page__notice {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  margin-bottom: var(--space-3);
}

.settings-page__notice strong {
  font-weight: 600;
}

.settings-page__notice--warning {
  border: 1px solid var(--warning);
  color: var(--warning);
  background: color-mix(in oklch, var(--warning) 10%, transparent);
}

.settings-page__notice--info {
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.settings-page__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding-top: var(--space-3);
}

.settings-page__danger {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.settings-page__danger-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}
</style>
