<script setup>
import { computed, ref } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import FormField from '../../components/ui/FormField.vue'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const isDirty = computed(() => store.isDirtySettings)

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
        <FormField label="Server Name">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="My Minecraft Server"
              v-model="store.serverSettings.name"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Bug Report URL" hint="Shown in support commands">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="url"
              placeholder="https://example.com/issues"
              v-model="store.serverSettings.bugReportLink"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField label="Message of the Day" :hint="`${motdCharacters}/59 characters`">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              maxlength="59"
              placeholder="Welcome to Fabricator"
              v-model="store.serverSettings.motd"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Server Port" hint="Default 25565">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="1024"
              max="65535"
              v-model.number="store.serverSettings.port"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField label="Bind Address (optional)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="0.0.0.0"
              v-model="store.serverSettings.serverIp"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Max Players">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="1"
              max="1000"
              v-model.number="store.serverSettings.maxPlayers"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField label="Running Version" hint="Version changes require reinstall">
          <template #default="{ id, describedBy }">
            <div class="settings-page__readonly">
              <input
                :id="id"
                class="settings-page__input"
                type="text"
                :value="store.serverStatus.version"
                readonly
                :aria-describedby="describedBy"
              />
              <span class="settings-page__readonly-badge">Read-only</span>
            </div>
          </template>
        </FormField>
        <FormField label="Mod Loader" hint="Loader changes require reinstall">
          <template #default="{ id, describedBy }">
            <div class="settings-page__readonly">
              <input
                :id="id"
                class="settings-page__input"
                type="text"
                :value="store.serverStatus.loader"
                readonly
                :aria-describedby="describedBy"
              />
              <span class="settings-page__readonly-badge">Read-only</span>
            </div>
          </template>
        </FormField>
      </div>
    </Panel>

    <Panel title="Gameplay">
      <div class="settings-page__grid">
        <FormField label="Difficulty">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.difficulty"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="peaceful">Peaceful</option>
              <option value="easy">Easy</option>
              <option value="normal">Normal</option>
              <option value="hard">Hard</option>
            </select>
          </template>
        </FormField>
        <FormField label="Default Gamemode">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.gamemode"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="survival">Survival</option>
              <option value="creative">Creative</option>
              <option value="adventure">Adventure</option>
              <option value="spectator">Spectator</option>
            </select>
          </template>
        </FormField>

        <FormField label="Spawn Protection (blocks)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              max="128"
              v-model.number="store.serverSettings.spawnProtection"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Idle Timeout (minutes)" hint="0 disables idle kick">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              max="10080"
              v-model.number="store.serverSettings.playerIdleTimeout"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField label="Pause When Empty (seconds)">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="0"
                max="3600"
                v-model.number="store.serverSettings.pauseWhenEmptySeconds"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField label="Function Permission Level">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1"
                max="4"
                v-model.number="store.serverSettings.functionPermissionLevel"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField label="Operator Permission Level">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1"
                max="4"
                v-model.number="store.serverSettings.opPermissionLevel"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
        </template>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.forceGamemode"
          label="Force Gamemode"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.hardcore"
          label="Hardcore"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.allowFlight"
          label="Allow Flight"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.pvp"
          label="Enable PvP"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.whitelist"
          label="Enable Whitelist"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.enforceWhitelist"
          label="Enforce Whitelist"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.commandBlocks"
          label="Enable Command Blocks"
          :disabled="!store.canEditSettings"
        />
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
        <FormField label="World Folder Name">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              v-model="store.serverSettings.levelName"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="World Type">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.levelType"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="default">Default</option>
              <option value="flat">Flat</option>
              <option value="large_biomes">Large Biomes</option>
              <option value="amplified">Amplified</option>
            </select>
          </template>
        </FormField>

        <FormField label="Seed">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="Leave empty for random"
              v-model="store.serverSettings.seed"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField v-if="showAdvanced" label="Generator Settings (JSON)">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="{}"
              v-model="store.serverSettings.generatorSettings"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField label="Max World Size">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxWorldSize"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField label="Entity Broadcast Range (%)">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="10"
                max="500"
                v-model.number="store.serverSettings.entityBroadcastRangePercentage"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField label="Max Chained Neighbor Updates">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxChainedNeighborUpdates"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
        </template>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.generateStructures"
          label="Generate Structures"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnAnimals"
          label="Spawn Animals"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnMonsters"
          label="Spawn Monsters"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnNpcs"
          label="Spawn NPCs"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <Panel v-if="showAdvanced" title="Resources & Packs">
      <div class="settings-page__grid">
        <FormField label="Resource Pack URL">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="url"
              placeholder="https://example.com/resource.zip"
              v-model="store.serverSettings.resourcePack"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Resource Pack SHA-1">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="40 character hash"
              v-model="store.serverSettings.resourcePackSha1"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField label="Resource Pack ID">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              v-model="store.serverSettings.resourcePackId"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Resource Pack Prompt">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="Displayed when joining"
              v-model="store.serverSettings.resourcePackPrompt"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.requireResourcePack"
          label="Require Players to Accept Pack"
          :disabled="!store.canEditSettings"
        />
      </div>

      <div class="settings-page__grid">
        <FormField label="Enabled Data Packs" hint="Comma separated identifiers">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="vanilla"
              v-model="store.serverSettings.initialEnabledPacks"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
        <FormField label="Disabled Data Packs">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              v-model="store.serverSettings.initialDisabledPacks"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" title="Networking & Connectivity">
      <div class="settings-page__grid settings-page__grid--three">
        <div class="settings-page__field">
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
        </div>
        <FormField label="Rate Limit (packets/second)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              v-model.number="store.serverSettings.rateLimit"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Compression Threshold (bytes)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="-1"
              v-model.number="store.serverSettings.networkCompressionThreshold"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <div class="settings-page__field">
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
        </div>
        <div class="settings-page__field">
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
        </div>
        <FormField label="RCON Password">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="password"
              v-model="store.serverSettings.rconPassword"
              :disabled="rconDisabled"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.onlineMode"
          label="Online Mode (Mojang Auth)"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.enforceSecureProfile"
          label="Enforce Secure Profiles"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.hideOnlinePlayers"
          label="Hide Player Count"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.preventProxyConnections"
          label="Prevent Proxy Connections"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.logIps"
          label="Log Player IPs"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.acceptsTransfers"
          label="Accept Transfers From Proxy"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.useNativeTransport"
          label="Use Native Transport"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.syncChunkWrites"
          label="Sync Chunk Writes"
          :disabled="!store.canEditSettings"
        />
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
        <FormField label="Memory Allocation (GB)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="1"
              max="64"
              step="0.5"
              v-model.number="store.serverSettings.memory"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="View Distance (chunks)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="3"
              max="32"
              v-model.number="store.serverSettings.viewDistance"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField label="Simulation Distance (chunks)">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="3"
              max="32"
              v-model.number="store.serverSettings.simulationDistance"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField label="Max Tick Time (ms)">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxTickTime"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField label="Region File Compression">
            <template #default="{ id, describedBy }">
              <select
                :id="id"
                class="settings-page__select"
                v-model="store.serverSettings.regionFileCompression"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              >
                <option value="deflate">Deflate</option>
                <option value="gzip">Gzip</option>
                <option value="lz4">LZ4</option>
                <option value="zstd">Zstd</option>
              </select>
            </template>
          </FormField>
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

        <FormField label="Text Filtering Config">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="{}"
              v-model="store.serverSettings.textFilteringConfig"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
        <FormField label="Text Filtering Version">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              v-model.number="store.serverSettings.textFilteringVersion"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.enableCodeOfConduct"
          label="Enable Code of Conduct"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.enableJmxMonitoring"
          label="Enable JMX Monitoring"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <Panel title="Danger zone">
      <div class="settings-page__danger">
        <p class="settings-page__danger-text">Deleting a server removes its files and backups. This cannot be undone.</p>
        <AppButton variant="danger" :loading="store.deletingServer" @click="store.openDeleteServerModal">
          {{ store.deletingServer ? 'Deleting…' : 'Delete server' }}
        </AppButton>
      </div>
    </Panel>

    <footer class="settings-page__footer" aria-label="Settings actions">
      <div class="settings-page__footer-inner">
        <AppButton
          variant="ghost"
          :disabled="!isDirty || !store.canEditSettings"
          @click="onReset"
        >
          Reset
        </AppButton>
        <AppButton
          variant="primary"
          :disabled="!isDirty || !store.canEditSettings"
          @click="onSave"
        >
          Save Changes
        </AppButton>
      </div>
    </footer>
  </div>
  <div v-else class="settings-page__loading">Loading settings…</div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 880px;
  padding-bottom: 80px;
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
  flex-direction: column;
  gap: 0;
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
  position: fixed;
  bottom: 0;
  left: var(--sidebar-width);
  right: 0;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-color);
  box-shadow: var(--shadow-up);
  padding: var(--space-4) var(--space-5);
  z-index: 10;
}

.settings-page__footer-inner {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
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
