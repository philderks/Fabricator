<template>
  <BaseModal 
    :show="show" 
    title="Create New Server" 
    size="large"
    @close="handleClose"
  >
    <div v-if="installState === 'installing'" class="install-progress-pane">
      <h3>Installing {{ formData.name }}…</h3>
      <p class="install-progress-phase">{{ phaseLabel(installProgress?.phase) }}</p>

      <div
        v-if="installProgress?.bytes_total > 0"
        class="install-progress-bar-wrap"
      >
        <div
          class="install-progress-bar-fill"
          :style="{ width: ((installProgress.bytes_done / installProgress.bytes_total) * 100) + '%' }"
        ></div>
        <span class="install-progress-bytes">
          {{ Math.round(installProgress.bytes_done / 1024) }} KB
          / {{ Math.round(installProgress.bytes_total / 1024) }} KB
        </span>
      </div>
      <div v-else class="install-progress-spinner" aria-label="Working…"></div>

      <p
        class="install-progress-hint"
        v-if="installProgress?.phase === 'installing_modpack' && modpackStageLabel(installProgress)"
      >
        {{ modpackStageLabel(installProgress) }}
      </p>

      <p class="install-progress-hint" v-if="installProgress?.phase === 'running_installer'">
        Forge / NeoForge installers download libraries and patch the vanilla server jar.
        This step can take several minutes for modern Minecraft versions.
      </p>

      <div class="install-progress-actions">
        <AppButton variant="ghost" size="md" @click="handleInstallClose">
          Close (continues in background)
        </AppButton>
      </div>
    </div>

    <div v-else-if="installState === 'failed'" class="install-failed-pane">
      <h3>Installation failed</h3>
      <p class="install-failed-error">{{ installProgress?.error || 'Unknown error.' }}</p>
      <div class="install-failed-actions">
        <AppButton variant="primary" size="md" @click="handleInstallRetry">Retry</AppButton>
        <AppButton variant="ghost" size="md" @click="handleInstallClose">Close</AppButton>
      </div>
    </div>

    <form v-else @submit.prevent="handleCreate" class="settings-form">
      <!-- Basic Settings -->
      <Panel title="Basic Settings">
        <FormField label="Server Name">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              v-model="formData.name"
              type="text"
              placeholder="My Minecraft Server"
              :aria-describedby="describedBy"
              required
            >
          </template>
        </FormField>

        <div class="form-row">
          <div class="form-group">
            <div class="version-label-row">
              <label for="minecraft-version">Minecraft Version</label>
              <label class="snapshot-toggle">
                <input type="checkbox" v-model="showSnapshots">
                <span>Show snapshots</span>
              </label>
            </div>
            <select
              id="minecraft-version"
              v-model="formData.version"
              @change="handleVersionChange"
              :disabled="versionsLoading || !filteredGameVersions.length"
              required
            >
              <option v-if="versionsLoading" disabled value="">Loading versions...</option>
              <option v-else-if="!versionsLoading && !filteredGameVersions.length" disabled value="">
                No versions available
              </option>
              <option
                v-for="version in filteredGameVersions"
                :key="version.version"
                :value="version.version"
              >
                {{ version.version }}
              </option>
            </select>
            <span v-if="requiredJavaText" class="form-hint">{{ requiredJavaText }}</span>
            <span v-if="javaRequirementWarning" class="form-hint warning-hint">{{ javaRequirementWarning }}</span>
          </div>

          <FormField label="Mod Loader">
            <template #default="{ id, describedBy }">
              <select
                :id="id"
                v-model="formData.loader"
                :aria-describedby="describedBy"
                required
              >
                <!-- Default: no loader preselected, so the choice is always
                     deliberate. Disabled so it can't be picked back. -->
                <option value="" disabled>None</option>
                <option
                  v-for="loaderOption in loaderOptions"
                  :key="loaderOption.value"
                  :value="loaderOption.value"
                >
                  {{ loaderOption.label }}
                </option>
              </select>
            </template>
          </FormField>
        </div>

        <div class="form-row">
          <FormField label="Server Port" hint="Default: 25565">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model.number="formData.port"
                type="number"
                min="1024"
                max="65535"
                placeholder="25565"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>

          <FormField label="Installation Path" hint="Where server files will be stored">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model="formData.installPath"
                type="text"
                placeholder="Leave empty for auto-generated path"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>
        </div>
      </Panel>

      <!-- Modpack Setup — only mod loaders use Modrinth modpacks (.mrpack).
           Vanilla has no loader, and plugin servers (Paper/Purpur/Folia/Pufferfish)
           use plugins, not modpacks. -->
      <Panel v-if="showModpackPanel" title="Modpack Setup">

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
          Use custom mode for manual setup, or choose a Modrinth modpack by link, by search,
          or by uploading a .mrpack file you exported yourself.
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
              <label class="choice-pill">
                <input type="radio" v-model="formData.modpackImportMethod" value="file">
                <span>Upload .mrpack</span>
              </label>
            </div>
          </div>

          <div v-if="formData.modpackImportMethod === 'link'" class="form-row modpack-input-row">
            <div class="form-group modpack-grow">
              <FormField label="Modpack URL or Slug" hint="Supports Modrinth links, slugs, or project IDs.">
                <template #default="{ id, describedBy }">
                  <input
                    :id="id"
                    v-model="modpackLinkInput"
                    type="text"
                    placeholder="https://modrinth.com/modpack/your-pack"
                    :aria-describedby="describedBy"
                  >
                </template>
              </FormField>
            </div>
            <div class="form-group modpack-action">
              <label>&nbsp;</label>
              <AppButton
                variant="ghost"
                size="md"
                :disabled="modpackLookupLoading || !modpackLinkInput.trim()"
                :loading="modpackLookupLoading"
                @click="resolveModpackByLink"
              >
                {{ modpackLookupLoading ? 'Resolving' : 'Resolve' }}
              </AppButton>
            </div>
          </div>

          <div v-else-if="formData.modpackImportMethod === 'search'">
            <div class="form-row modpack-input-row">
              <div class="form-group modpack-grow">
                <FormField label="Search Modpacks">
                  <template #default="{ id, describedBy }">
                    <input
                      :id="id"
                      v-model="modpackSearchQuery"
                      type="text"
                      placeholder="All of Fabric, Better Minecraft, ..."
                      :aria-describedby="describedBy"
                    >
                  </template>
                </FormField>
              </div>
              <div class="form-group modpack-action">
                <label>&nbsp;</label>
                <AppButton
                  variant="ghost"
                  size="md"
                  :disabled="modpackSearchLoading || !modpackSearchQuery.trim()"
                  :loading="modpackSearchLoading"
                  @click="searchForModpacks"
                >
                  {{ modpackSearchLoading ? 'Searching' : 'Search' }}
                </AppButton>
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

          <!-- Upload a .mrpack exported from the Modrinth app (#53). The pack
               declares its own Minecraft version and loader, so selecting one
               fills those fields in — editable afterwards, with a warning if
               they end up disagreeing with the pack. -->
          <div v-else class="mrpack-upload">
            <FormField
              label="Modpack File"
              hint="A .mrpack exported by the Modrinth app. Mods are fetched from Modrinth; config and other extras come from the pack's overrides."
            >
              <template #default="{ id, describedBy }">
                <input
                  :id="id"
                  ref="mrpackInput"
                  type="file"
                  accept=".mrpack,application/zip"
                  :disabled="packUploading"
                  :aria-describedby="describedBy"
                  @change="handlePackFileChange"
                >
              </template>
            </FormField>

            <div v-if="packUploading" class="mrpack-progress">
              <div class="mrpack-progress-track">
                <div
                  class="mrpack-progress-fill"
                  :class="{ indeterminate: packUploadPercent < 0 }"
                  :style="packUploadPercent >= 0 ? { width: `${packUploadPercent}%` } : null"
                ></div>
              </div>
              <span>{{ packUploadPercent >= 0 ? `Uploading ${packUploadPercent}%` : 'Uploading…' }}</span>
            </div>

            <p v-if="packUploadError" class="modpack-error">{{ packUploadError }}</p>
          </div>

          <p v-if="modpackError" class="modpack-error">{{ modpackError }}</p>

          <div v-if="selectedModpack" class="modpack-selected">
            <div>
              <p class="selected-label">Selected Modpack</p>
              <strong>{{ selectedModpack.title }}</strong>
              <p>{{ selectedModpack.description || 'No description provided.' }}</p>
            </div>
            <AppButton variant="ghost" size="sm" @click="clearSelectedModpack">
              Clear
            </AppButton>
          </div>

          <div v-if="uploadedPack" class="modpack-selected">
            <div>
              <p class="selected-label">Uploaded Modpack</p>
              <strong>{{ uploadedPackTitle }}</strong>
              <p>{{ uploadedPackDetail }}</p>
            </div>
            <AppButton variant="ghost" size="sm" :disabled="creating" @click="clearUploadedPack">
              Clear
            </AppButton>
          </div>

          <p v-if="packMismatchWarning" class="modpack-warning">{{ packMismatchWarning }}</p>

        </div>
      </Panel>

      <!-- Gameplay Settings -->
      <Panel title="Gameplay">

        <div class="form-row">
          <FormField label="Max Players">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model.number="formData.maxPlayers"
                type="number"
                min="1"
                max="1000"
                placeholder="20"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>

          <FormField label="Difficulty">
            <template #default="{ id, describedBy }">
              <select :id="id" v-model="formData.difficulty" :aria-describedby="describedBy">
                <option value="peaceful">Peaceful</option>
                <option value="easy">Easy</option>
                <option value="normal">Normal</option>
                <option value="hard">Hard</option>
              </select>
            </template>
          </FormField>
        </div>

        <div class="form-row">
          <FormField label="Default Gamemode">
            <template #default="{ id, describedBy }">
              <select :id="id" v-model="formData.gamemode" :aria-describedby="describedBy">
                <option value="survival">Survival</option>
                <option value="creative">Creative</option>
                <option value="adventure">Adventure</option>
                <option value="spectator">Spectator</option>
              </select>
            </template>
          </FormField>

          <FormField label="View Distance" hint="3-32 chunks">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model.number="formData.viewDistance"
                type="number"
                min="3"
                max="32"
                placeholder="10"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>
        </div>
      </Panel>

      <!-- World Settings -->
      <Panel title="World">

        <FormField label="World Name" hint="Folder name for world files">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              v-model="formData.levelName"
              type="text"
              placeholder="world"
              :aria-describedby="describedBy"
            >
          </template>
        </FormField>

        <div class="form-row">
          <FormField label="World Type">
            <template #default="{ id, describedBy }">
              <select :id="id" v-model="formData.levelType" :aria-describedby="describedBy">
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
                v-model="formData.seed"
                type="text"
                placeholder="Leave empty for random"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>
        </div>

        <FormField label="Java Executable Path (Optional)" hint="Use a specific Java runtime for this server.">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              v-model.trim="formData.javaPath"
              @blur="refreshJavaRequirement"
              type="text"
              placeholder="java or /path/to/java"
              :aria-describedby="describedBy"
            >
          </template>
        </FormField>

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
      </Panel>

      <!-- Advanced Settings -->
      <Panel title="Advanced">

        <div class="form-row">
          <FormField label="Memory Allocation (GB)">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model.number="formData.memory"
                type="number"
                min="1"
                max="32"
                step="0.5"
                placeholder="4"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>

          <FormField label="Simulation Distance">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                v-model.number="formData.simulationDistance"
                type="number"
                min="3"
                max="32"
                placeholder="10"
                :aria-describedby="describedBy"
              >
            </template>
          </FormField>
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

        <FormField label="MOTD (Message of the Day)" :hint="`${formData.motd.length}/59 characters`">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              v-model="formData.motd"
              rows="2"
              placeholder="A Minecraft Server"
              maxlength="59"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
      </Panel>

      <!-- EULA Agreement -->
      <Panel title="Minecraft EULA">
        <label class="create-eula">
          <input type="checkbox" v-model="formData.acceptEula" required>
          <div class="create-eula__body">
            <span class="create-eula__primary">
              I agree to the
              <a href="https://www.minecraft.net/en-us/eula" target="_blank" rel="noopener noreferrer">
                Minecraft EULA
              </a>
            </span>
            <p class="create-eula__notice">
              By creating a server, you must accept Mojang's End User License Agreement. This is required to run a Minecraft server.
            </p>
          </div>
        </label>
      </Panel>
    </form>

    <template #footer>
      <template v-if="!installState">
        <AppButton variant="ghost" size="md" :disabled="creating" @click="handleClose">
          Cancel
        </AppButton>
        <AppButton
          variant="primary"
          size="md"
          :disabled="creating || !formData.acceptEula"
          :loading="creating"
          @click="handleCreate"
        >
          {{ creating ? 'Creating' : 'Create Server' }}
        </AppButton>
      </template>
    </template>
  </BaseModal>


  <JavaInstallModal
    :show="showJavaModal"
    :mc-version="pendingJavaMcVersion"
    @close="showJavaModal = false"
    @java-installed="handleJavaInstalled"
  />

</template>

<script>
import BaseModal from './BaseModal.vue'
import JavaInstallModal from './JavaInstallModal.vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import { createServer, installServer, getLoaderGameVersions, getJavaStatus, getServerInstallProgress } from '../../api/servers'
import {
  resolveProjectVersion,
  uploadModpackArchive,
  discardModpackUpload
} from '../../api/modrinth'
import { useToast } from '../../composables/useToast'
import { useModpackImport } from '../../composables/useModpackImport'
import { formatNumber } from '../../utils/format'
import { loaderContentKind } from '../../utils/loaderKind'

export default {
  name: 'ServerCreateModal',
  components: {
    BaseModal,
    JavaInstallModal,
    Panel,
    AppButton,
    FormField
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
    return { toast, formatNumber }
  },
  data() {
    return {
      creating: false,
      // Phase 3c: install-progress state. Modal flips into 'installing' or
      // 'failed' once the user submits and the backend returns 202; the
      // existing 'creating' flag stays true during this phase to keep the
      // submit button disabled if the modal is somehow re-rendered.
      installState: null,           // null | 'installing' | 'failed'
      installProgress: null,         // last-seen progress payload from GET /install/progress
      installPollHandle: null,       // setInterval handle; clear on terminal/unmount
      installPollResolver: null,     // Promise resolve fn so handleInstallClose can release a mid-install await
      installCreatedServerId: null,  // server.id that the install ran against (for retry)
      versionsLoading: false,
      imp: null,
      showJavaModal: false,
      pendingJavaMcVersion: '',
      pendingJavaRetryServerId: null,
      uploadedPack: null,
      packUploading: false,
      packUploadPercent: 0,
      packUploadError: '',
      packUploadAbort: null,
      // A pack's Minecraft version, held until the version list that has to
      // contain it finishes loading. See applyPendingPackVersion.
      pendingPackVersion: '',
      gameVersions: [],
      showSnapshots: false,
      javaStatus: null,
      javaRequirementWarning: '',
      loaderOptions: [
        { value: 'fabric',     label: 'Fabric'     },
        { value: 'quilt',      label: 'Quilt'      },
        { value: 'neoforge',   label: 'NeoForge'   },
        { value: 'forge',      label: 'Forge'      },
        { value: 'paper',      label: 'Paper'      },
        { value: 'purpur',     label: 'Purpur'     },
        { value: 'folia',      label: 'Folia'      },
        { value: 'pufferfish', label: 'Pufferfish' },
        { value: 'vanilla',    label: 'Vanilla'    }
      ],
      formData: {
        setupMode: 'custom',
        modpackImportMethod: 'link',
        name: '',
        version: '',
        loader: '',
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
        motd: 'A Minecraft Server managed by Fabricator',
        acceptEula: false
      }
    };
  },
  created() {
    this.imp = useModpackImport({
      mcVersion: () => this.formData.version,
      loader: () => this.formData.loader
    })
    this.loadGameVersions()
  },
  computed: {
    showModpackPanel() {
      // Only true mod loaders (Fabric/Quilt/Forge/NeoForge) support .mrpack.
      // The empty "None" default is excluded explicitly: loaderContentKind
      // fails open to 'mod' for anything it doesn't recognise, which is right
      // for a real server whose loader tab must not vanish, but wrong here —
      // no loader picked yet means no modpack story to offer.
      return Boolean(this.formData.loader) && loaderContentKind(this.formData.loader) === 'mod'
    },
    filteredGameVersions() {
      if (this.showSnapshots) return this.gameVersions
      return this.gameVersions.filter(v => v.stable)
    },
    selectedModpack() {
      return this.imp?.selectedModpack ?? null
    },
    modpackLinkInput: {
      get() { return this.imp?.modpackLink ?? '' },
      set(v) { if (this.imp) this.imp.modpackLink = v }
    },
    modpackSearchQuery: {
      get() { return this.imp?.searchQuery ?? '' },
      set(v) { if (this.imp) this.imp.searchQuery = v }
    },
    modpackSearchResults() {
      return this.imp?.searchResults ?? []
    },
    modpackSearchDone() {
      return this.imp?.searchDone ?? false
    },
    modpackLookupLoading() {
      return this.imp?.resolving ?? false
    },
    modpackSearchLoading() {
      return this.imp?.loading ?? false
    },
    modpackError: {
      get() { return this.imp?.errorMessage?.value ?? '' },
      set(v) { if (this.imp?.errorMessage) this.imp.errorMessage.value = v }
    },
    uploadedPackTitle() {
      return this.uploadedPack?.name || this.uploadedPack?.filename || 'Uploaded modpack'
    },
    uploadedPackDetail() {
      if (!this.uploadedPack) {
        return ''
      }
      const parts = []
      if (this.uploadedPack.version) parts.push(`Version ${this.uploadedPack.version}`)
      if (this.uploadedPack.minecraft_version) parts.push(`Minecraft ${this.uploadedPack.minecraft_version}`)
      if (this.uploadedPack.loader) parts.push(this.loaderLabelFor(this.uploadedPack.loader))
      const fileCount = this.uploadedPack.file_count || 0
      if (fileCount) parts.push(`${fileCount} file${fileCount === 1 ? '' : 's'}`)
      return parts.join(' · ')
    },
    packMismatchWarning() {
      // The fields stay editable after a pack fills them in, so say plainly
      // when they have drifted from what the pack was built against. Creating
      // anyway is allowed — only the user knows if the pack is portable.
      if (!this.uploadedPack) {
        return ''
      }
      const differences = []
      const packMc = this.uploadedPack.minecraft_version || ''
      const packLoader = (this.uploadedPack.loader || '').toLowerCase()
      if (packMc && this.formData.version && packMc !== this.formData.version) {
        differences.push(`Minecraft ${packMc}`)
      }
      if (packLoader && this.formData.loader && packLoader !== this.formData.loader) {
        differences.push(this.loaderLabelFor(packLoader))
      }
      if (!differences.length) {
        return ''
      }
      return `This pack was built for ${differences.join(' and ')}. You can create the server anyway, but the pack may not run on this setup.`
    },
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
  },
  watch: {
    showSnapshots(val) {
      if (!val) {
        const currentVersion = this.gameVersions.find(v => v.version === this.formData.version)
        if (currentVersion && !currentVersion.stable) {
          const firstStable = this.gameVersions.find(v => v.stable)
          if (firstStable) {
            this.formData.version = firstStable.version
            this.refreshJavaRequirement()
          }
        }
      }
    },
    'formData.modpackImportMethod'(method) {
      // Link/search and upload are two answers to the same question. Leaving
      // both populated would make the install path ambiguous — and the one
      // still on screen is the one the user means.
      if (method === 'file') {
        this.clearSelectedModpack()
      } else {
        this.clearUploadedPack()
      }
    },
    'formData.loader'(newLoader, oldLoader) {
      if (newLoader === oldLoader) return
      // Deliberately NOT clearing formData.version here. Picking the version
      // first and the loader second is a normal order, and wiping the choice
      // made loadGameVersions treat it as "nothing picked" and drop the newest
      // stable release on top of it. That reload already replaces the version
      // when the incoming loader has no build for it, so leaving it alone keeps
      // a still-valid choice and fixes an unsupported one.
      // Loaders without a modpack story (Vanilla + plugin servers) — flip back
      // to custom and drop any cached modpack selection so a stale modpack
      // URL/object doesn't ride along into the create POST and trip a 409.
      if (loaderContentKind(newLoader) !== 'mod') {
        this.formData.setupMode = 'custom'
        if (this.imp?.selectedModpack) {
          this.imp.selectedModpack.value = null
        }
        this.pendingPackVersion = ''
        this.clearUploadedPack()
      }
      this.loadGameVersions()
    }
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
        acceptEula: this.formData.acceptEula,
        javaPath: this.formData.javaPath || undefined
      }
    },

    resolveModpackByLink() {
      return this.imp.resolveByLink()
    },

    searchForModpacks() {
      return this.imp.performSearch()
    },

    selectModpackFromSearch(pack) {
      this.imp.selectPack(pack)
    },

    clearSelectedModpack() {
      this.imp.clearSelection()
    },

    loaderLabelFor(loader) {
      const value = String(loader || '').toLowerCase()
      const known = this.loaderOptions.find(option => option.value === value)
      return known ? known.label : value
    },

    async handlePackFileChange(event) {
      const file = event?.target?.files?.[0]
      if (!file) {
        return
      }

      // Replacing one file with another: release the pack already staged.
      await this.clearUploadedPack({ keepInput: true })

      this.packUploading = true
      this.packUploadPercent = 0
      this.packUploadError = ''
      try {
        const pack = await uploadModpackArchive(file, {
          onProgress: (pct) => { this.packUploadPercent = pct },
          registerAbort: (abort) => { this.packUploadAbort = abort }
        })
        this.uploadedPack = pack
        await this.applyPackDefaults(pack)
      } catch (error) {
        this.resetPackFileInput()
        // Cancelling is something the user just did (closed the dialog); only
        // a real failure is news. The message is the one api/modrinth.js
        // raises on xhr.onabort.
        if (error?.message === 'Upload cancelled') {
          return
        }
        this.packUploadError = error?.message || 'Could not read that .mrpack file.'
        this.toast.error(this.packUploadError, 'Modpack Upload Failed')
      } finally {
        this.packUploading = false
        this.packUploadAbort = null
      }
    },

    /** Fill the loader and Minecraft version in from what the pack declares. */
    async applyPackDefaults(pack) {
      const packLoader = String(pack?.loader || '').toLowerCase()
      const packVersion = pack?.minecraft_version || ''

      if (packVersion) {
        this.pendingPackVersion = packVersion
      }

      const supported = this.loaderOptions.some(option => option.value === packLoader)
      if (packLoader && !supported) {
        this.toast.warning(
          `This pack targets ${packLoader}, which Fabricator cannot install. Pick a loader yourself.`,
          'Unsupported Loader',
        )
      }

      if (packLoader && supported && packLoader !== this.formData.loader) {
        // The loader watcher reloads the version list; the pack's version is
        // applied from there, once the list that must contain it exists.
        this.formData.loader = packLoader
        return
      }

      await this.applyPendingPackVersion()
      await this.refreshJavaRequirement()
    },

    /** Apply a pack's Minecraft version against the loaded version list. */
    async applyPendingPackVersion() {
      const wanted = this.pendingPackVersion
      if (!wanted) {
        return
      }
      this.pendingPackVersion = ''

      const match = this.gameVersions.find(v => v.version === wanted)
      if (!match) {
        this.toast.warning(
          `This pack targets Minecraft ${wanted}, which this loader has no build for. Pick a version yourself.`,
          'Version Unavailable',
        )
        return
      }
      // A pack pinned to a snapshot would otherwise be filtered out of the
      // select the moment we set it.
      if (!match.stable) {
        this.showSnapshots = true
      }
      this.formData.version = wanted
    },

    resetPackFileInput() {
      const input = this.$refs.mrpackInput
      if (input) {
        input.value = ''
      }
    },

    async clearUploadedPack({ keepInput = false } = {}) {
      if (this.packUploadAbort) {
        // Stops an in-flight upload from staging an archive nobody will
        // install — otherwise it sits until the backend's TTL sweep.
        this.packUploadAbort()
        this.packUploadAbort = null
      }
      const pack = this.uploadedPack
      this.uploadedPack = null
      this.packUploadError = ''
      this.packUploadPercent = 0
      if (!keepInput) {
        this.resetPackFileInput()
      }
      if (pack?.upload_id) {
        // Best effort: a staged pack the backend still holds expires on its
        // own, so a failed discard is not worth surfacing.
        try {
          await discardModpackUpload(pack.upload_id)
        } catch (_) {
          // ignore
        }
      }
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

    // The modpack the backend should install once the loader is in. Handing
    // the intent over with the install request is what makes it survive this
    // screen being closed or the page refreshed (#63) — previously the browser
    // had to still be here to fire a second request, and if it wasn't, the
    // pack was silently dropped.
    buildModpackIntent() {
      if (this.formData.setupMode !== 'modpack') return null
      if (this.uploadedPack) {
        return {
          source: 'upload',
          upload_id: this.uploadedPack.upload_id,
          loader: this.formData.loader,
          mc_version: this.formData.version,
        }
      }
      if (this.selectedModpack) {
        return {
          source: 'project',
          project_id: this.selectedModpack.id,
          loader: this.formData.loader,
          mc_version: this.formData.version,
        }
      }
      return null
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
        // With the "None" default nothing is picked yet, so list plain game
        // versions rather than some loader's subset. Picking a loader refetches
        // against that loader, so this list is only ever a starting point.
        const loader = this.formData.loader || 'vanilla'
        const previousVersion = this.formData.version
        const versions = await getLoaderGameVersions(loader)
        this.gameVersions = Array.isArray(versions) ? versions : []
        const stableVersions = this.gameVersions.filter(v => v.stable)
        const preferred = stableVersions[0] || this.gameVersions[0]
        const versionExists = this.filteredGameVersions.some(v => v.version === this.formData.version)
        if ((!this.formData.version || !versionExists) && preferred) {
          this.formData.version = preferred.version
          // Only when a real choice had to be dropped: the version genuinely
          // isn't offered for this loader. Silently swapping it is how the
          // reset bug went unnoticed. Skipped while a pack is pending, since
          // applyPendingPackVersion below has the final say on the version and
          // reports its own mismatch.
          if (previousVersion && previousVersion !== preferred.version && !this.pendingPackVersion) {
            this.toast.info(
              `${this.loaderLabelFor(loader)} has no build for Minecraft ${previousVersion} — switched to ${preferred.version}.`,
              'Version Changed',
            )
          }
        }
        // An uploaded pack's own Minecraft version outranks the newest-stable
        // default: switching the loader to match a pack reloads this list, and
        // the default would otherwise land on top of the pack's choice.
        await this.applyPendingPackVersion()
        await this.refreshJavaRequirement()
      } catch (error) {
        console.error('Failed to load game versions:', error)
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

      try {
        this.javaStatus = await getJavaStatus({
          mcVersion: this.formData.version,
          javaPath: this.formData.javaPath || undefined
        })
        this.javaRequirementWarning = this.javaStatus?.compatibility?.warning || ''
      } catch (error) {
        console.error('Failed to resolve Java requirement:', error)
        this.javaRequirementWarning = 'Could not verify Java requirement right now.'
      }
    },

    async handleVersionChange() {
      await this.refreshJavaRequirement()
    },
    
    openJavaModal({ createdServerId = null } = {}) {
      this.pendingJavaMcVersion = this.formData.version || ''
      this.pendingJavaRetryServerId = createdServerId
      this.showJavaModal = true
    },

    async handleJavaInstalled() {
      const retryServerId = this.pendingJavaRetryServerId
      this.showJavaModal = false
      this.pendingJavaRetryServerId = null
      if (retryServerId) {
        // Server was already created on the prior attempt; retry just the
        // install step. Phase 3c made /install async (returns 202 + initial
        // progress, real outcome arrives via polling) — mirror handleCreate's
        // post-202 flow so success/failure surfaces correctly. Without this,
        // the call silently no-ops because installResult?.success is undefined
        // on the new 202 body.
        this.installCreatedServerId = retryServerId
        this.installState = 'installing'
        this.installProgress = null
        try {
          const initialProgress = await installServer(retryServerId)
          this.installProgress = initialProgress
          const finalProgress = await this.pollInstallProgress(retryServerId)
          if (finalProgress.phase === 'aborted') {
            // User cancelled the retry mid-install via Close.
          } else if (finalProgress.phase === 'done') {
            this.toast.success('Server installed successfully.', 'Server Installation')
            this.installState = null
            this.installProgress = null
          } else {
            this.installState = 'failed'
            this.installProgress = finalProgress
            this.toast.error(
              finalProgress.error || 'Installation failed',
              'Server Installation Failed',
            )
          }
        } catch (error) {
          this.installState = 'failed'
          this.installProgress = { phase: 'failed', error: error?.message || 'Installation failed' }
          this.toast.error(error?.message || 'Installation failed', 'Server Installation Failed')
        }
      } else {
        // Pre-check path: retry the full create flow now that Java exists.
        this.handleCreate()
      }
    },

    phaseLabel(phase) {
      const labels = {
        starting:               'Preparing install…',
        resolving_versions:     'Resolving versions…',
        downloading_installer:  'Downloading installer…',
        downloading_server_jar: 'Downloading server jar…',
        verifying:              'Verifying download…',
        running_installer:      'Running installer (this can take 2–15 minutes)…',
        detecting_artifacts:    'Verifying artefacts…',
        writing_eula:           'Finalising…',
        installing_modpack:     'Installing modpack…',
        done:                   'Done',
        failed:                 'Failed',
      }
      return labels[phase] || 'Installing…'
    },

    /** Sub-stage detail while the worker is installing the modpack. */
    modpackStageLabel(progress) {
      const labels = {
        starting:              'Preparing…',
        resolving:             'Resolving modpack version…',
        downloading_pack:      'Downloading modpack archive…',
        checking_availability: 'Checking file availability…',
        installing_files:      'Downloading mods…',
        extracting_overrides:  'Extracting override files…',
        verifying_mod_sides:   'Checking mods for server compatibility…',
        done:                  'Finishing up…',
      }
      const label = labels[progress?.modpack_stage]
      if (!label) return ''
      if (progress.modpack_total > 0) {
        return `${label} (${progress.modpack_current}/${progress.modpack_total})`
      }
      return label
    },

    /**
     * Poll GET /install/progress until phase is terminal.
     * Resolves with the final progress payload ({phase, error?, ...}).
     * Updates this.installProgress on every poll so the template stays live.
     * Cleans up its own interval handle.
     */
    async pollInstallProgress(serverId) {
      return new Promise((resolve) => {
        // Stash the resolver so handleInstallClose can release this Promise
        // when the user clicks Close mid-install. Without that escape hatch,
        // clearInterval stops further ticks but leaves the awaiting handleCreate
        // hung — its finally never runs, this.creating stays true forever.
        this.installPollResolver = resolve
        const tick = async () => {
          try {
            const progress = await getServerInstallProgress(serverId)
            this.installProgress = progress
            if (!progress.active || progress.phase === 'done' || progress.phase === 'failed') {
              if (this.installPollHandle) {
                clearInterval(this.installPollHandle)
                this.installPollHandle = null
              }
              this.installPollResolver = null
              resolve(progress)
            }
          } catch (err) {
            // If the GET itself fails (rare — server unreachable), surface as failed.
            console.error('Install-progress poll failed:', err)
            if (this.installPollHandle) {
              clearInterval(this.installPollHandle)
              this.installPollHandle = null
            }
            this.installPollResolver = null
            resolve({ phase: 'failed', error: err.message || 'Lost contact with backend during install.' })
          }
        }
        // Tick once immediately so a fast install (e.g. Vanilla cached) resolves
        // without a 750ms wait, then on the interval.
        tick()
        this.installPollHandle = setInterval(tick, 750)
      })
    },

    handleInstallRetry() {
      // Reset install state and call handleCreate again. The form data is still
      // in place, so the same install runs against the same server record.
      this.installState = null
      this.installProgress = null
      // Re-use the same created server: skip the createServer step. Easiest is
      // to just call installServer directly and re-run the polling.
      // To keep things simple we re-trigger handleCreate, which will create a
      // NEW server record. If the user wants to retry the same record, they
      // can use the server-detail page's Install button. v1: new record on retry.
      // (Avoiding stale-record reuse simplifies error handling.)
      this.handleCreate()
    },

    handleInstallClose() {
      // Release the awaiting handleCreate Promise so its finally block runs
      // and `this.creating` flips back to false. resetForm only stops the
      // polling interval; the Promise itself stays pending without this.
      // Backend install thread continues — we just stop watching.
      if (this.installPollResolver) {
        this.installPollResolver({ phase: 'aborted' })
        this.installPollResolver = null
      }
      if (this.installState === 'installing') {
        this.toast.info(
          'Installation continues in the background. The server appears in your list when it\'s ready.',
          'Install Running',
        )
      }
      this.$emit('close')
      this.resetForm()
    },

    async handleCreate() {
      if (this.creating) return

      if (!this.formData.name.trim()) {
        this.toast.warning('Please enter a server name.', 'Name Required')
        return
      }

      if (!this.formData.version) {
        this.toast.warning('Please select a Minecraft version.', 'Version Required')
        return
      }

      // The loader select defaults to the empty "None" placeholder, so this is
      // a real path, not a defensive check. Native `required` can't cover it:
      // the Create button lives in the modal footer, outside the <form>.
      if (!this.formData.loader) {
        this.toast.warning('Please choose a mod loader.', 'Loader Required')
        return
      }

      if (!this.formData.acceptEula) {
        this.toast.warning('You must accept the Minecraft EULA to create a server.', 'EULA Required')
        return
      }

      if (this.formData.setupMode === 'modpack' && !this.selectedModpack && !this.uploadedPack) {
        this.toast.warning(
          'Choose a modpack by link or search, or upload a .mrpack, before creating the server.',
          'Modpack Required',
        )
        return
      }

      if (this.packUploading) {
        this.toast.warning('Wait for the modpack upload to finish.', 'Upload In Progress')
        return
      }

      // Only a Modrinth-hosted pack needs resolving; an uploaded one is
      // already here, and its mismatch warning has been on the form all along.
      if (this.formData.setupMode === 'modpack' && this.selectedModpack) {
        const compatible = await this.validateSelectedModpackCompatibility()
        if (!compatible) {
          return
        }
      }

      // Pre-flight Java check (existing — unchanged).
      try {
        const status = await getJavaStatus({
          mcVersion: this.formData.version,
          javaPath: this.formData.javaPath || undefined
        })
        const hasManaged = !!status?.managed_java?.installed
        const meetsRequirement = !!status?.meets_requirement || !!status?.system_java?.meets_requirement
        if (status?.required_java && !meetsRequirement && !hasManaged) {
          this.openJavaModal()
          return
        }
      } catch (err) {
        console.error('Java pre-check failed:', err)
      }

      this.creating = true
      this.installState = null
      this.installProgress = null
      this.installCreatedServerId = null

      try {
        const server = await createServer(this.buildServerPayload())
        this.installCreatedServerId = server.id

        // POST /install — 202 on async start; 400 (Java guard) throws into catch.
        // The modpack rides along so the worker installs it too; from here on
        // this screen only observes.
        const modpackIntent = this.buildModpackIntent()
        const initialProgress = await installServer(server.id, { modpack: modpackIntent })

        // Switch modal into install-progress UI and start polling.
        this.installState = 'installing'
        this.installProgress = initialProgress

        const finalProgress = await this.pollInstallProgress(server.id)

        if (finalProgress.phase === 'aborted') {
          // User clicked Close during install. Modal already closed and state
          // already reset by handleInstallClose; backend continues in
          // background. Nothing else to do — finally clears `creating`.
        } else if (finalProgress.phase === 'done') {
          // The worker installed the modpack too; report what it did rather
          // than doing it here.
          let modpackInstallError = null
          if (modpackIntent) {
            const modpackTitle = this.selectedModpack?.title || this.uploadedPackTitle
            // The backend consumes a staged upload once it lands, so drop our
            // handle before resetForm can try to discard it again.
            this.uploadedPack = null
            if (finalProgress.modpack_error) {
              modpackInstallError = finalProgress.modpack_error
              this.toast.error(modpackInstallError, 'Modpack Failed')
            } else {
              this.toast.success(`${modpackTitle} installed successfully!`, 'Modpack Installed')
              if (finalProgress.modpack_uncertain > 0) {
                this.toast.info(
                  `${finalProgress.modpack_uncertain} mods could not be confirmed as server-safe. Review them on the server's mods page.`,
                  'Modpack Warnings',
                )
              }
            }
          }

          this.$emit('create', { id: server.id, name: this.formData.name, modpackInstallError })
          this.$emit('close')
          this.resetForm()
        } else {
          // phase === 'failed' — show inline error UI, do NOT auto-close.
          this.installState = 'failed'
          this.installProgress = finalProgress
          // Server record exists but is in 'failed' status. User can Retry or Close.
        }
      } catch (error) {
        // 400 (Java guard) and other non-2xx errors land here.
        console.error('Failed to create/install server:', error)
        const isJavaIssue = error?.data?.java_missing || error?.data?.java_too_old
        if (isJavaIssue) {
          this.openJavaModal({ createdServerId: this.installCreatedServerId })
        } else {
          this.toast.error(error.message || 'Server creation failed', 'Server Creation Failed')
        }
        if (this.installCreatedServerId) {
          this.$emit('create', { id: this.installCreatedServerId, name: this.formData.name })
          this.$emit('close')
          this.resetForm({ keepJavaModal: isJavaIssue })
        }
      } finally {
        this.creating = false
        // installState handles the rest: 'installing' (still polling), 'failed' (UI),
        // null (success/close-emitted-already, modal will be unmounted).
      }
    },
    
    resetForm({ keepJavaModal = false } = {}) {
      const preservedVersion = this.formData.version
      this.formData = {
        setupMode: 'custom',
        modpackImportMethod: 'link',
        name: '',
        version: preservedVersion || (this.gameVersions[0]?.version || ''),
        loader: '',
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
      if (!keepJavaModal) {
        this.showJavaModal = false
        this.pendingJavaMcVersion = ''
        this.pendingJavaRetryServerId = null
      }

      if (this.imp) {
        this.imp.resetAll()
      }

      // Releases the staged archive server-side too, so closing the dialog
      // does not leave an upload sitting in the staging folder until it ages
      // out. A pack that was installed has already been cleared above.
      this.pendingPackVersion = ''
      this.packUploading = false
      this.clearUploadedPack()

      // Phase 3c: clear install-progress state so re-opening the modal starts clean.
      this.installState = null
      this.installProgress = null
      this.installCreatedServerId = null
      this.installPollResolver = null
      if (this.installPollHandle) {
        clearInterval(this.installPollHandle)
        this.installPollHandle = null
      }
    }
  },
  beforeUnmount() {
    if (this.installPollHandle) {
      clearInterval(this.installPollHandle)
      this.installPollHandle = null
    }
  }
}
</script>

<style scoped>
/* Form layout — wraps the Panel stack */
.settings-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.version-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.snapshot-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  font-weight: 400;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.snapshot-toggle input[type="checkbox"] {
  width: auto;
  margin: 0;
  cursor: pointer;
  accent-color: var(--primary);
}

.warning-hint {
  color: var(--warning);
}

/* Mode toggle (Custom Server / Import Modpack) */
.mode-toggle {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  gap: 2px;
}

.mode-toggle-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-weight: 600;
  font-size: var(--text-xs);
  font-family: inherit;
  transition: background 0.15s ease, color 0.15s ease;
}

.mode-toggle-btn:hover:not(.active) {
  color: var(--text-secondary);
}

.mode-toggle-btn.active {
  background: var(--primary);
  color: white;
}

/* Modpack subform */
.modpack-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
}

.inline-choice {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.choice-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: 6px var(--space-3);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.choice-pill input[type="radio"] {
  accent-color: var(--primary);
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
  gap: var(--space-3);
}

.modpack-result {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
  font-family: inherit;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.modpack-result:hover {
  border-color: var(--border-hover);
}

.modpack-result.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--primary) 20%, transparent);
}

.modpack-result-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.modpack-result-header strong {
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.modpack-result-header p {
  margin: 2px 0 0;
  color: var(--text-muted);
  font-size: var(--text-xs);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.modpack-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

.modpack-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  object-fit: cover;
  border: 1px solid var(--border-color);
  flex-shrink: 0;
}

.modpack-error {
  margin: 0;
  color: var(--danger);
  font-size: var(--text-xs);
}

.modpack-warning {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--warning) 28%, transparent);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

/* .mrpack upload */
.mrpack-upload {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.mrpack-upload input[type="file"] {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.mrpack-upload input[type="file"]:disabled {
  opacity: 0.6;
  cursor: progress;
}

.mrpack-progress {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.mrpack-progress-track {
  flex: 1;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.mrpack-progress-fill {
  height: 100%;
  background: var(--primary);
  transition: width 0.2s ease;
}

/* No length in the progress events — show motion rather than a false number. */
.mrpack-progress-fill.indeterminate {
  width: 40%;
  animation: mrpack-progress-slide 1.1s ease-in-out infinite;
}

@keyframes mrpack-progress-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(250%); }
}

.modpack-selected {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  align-items: start;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: color-mix(in oklch, var(--success) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--success) 28%, transparent);
}

.modpack-selected p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.modpack-selected strong {
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.selected-label {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* EULA panel */
.create-eula {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  cursor: pointer;
}

.create-eula input[type="checkbox"] {
  width: 18px;
  height: 18px;
  margin-top: 2px;
  cursor: pointer;
  accent-color: var(--primary);
  flex-shrink: 0;
}

.create-eula__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.create-eula__primary {
  font-size: var(--text-sm);
  color: var(--text-primary);
  user-select: none;
  line-height: var(--leading-normal);
}

.create-eula__primary a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
  border-bottom: 1px solid transparent;
  transition: border-color 0.15s;
}

.create-eula__primary a:hover {
  border-bottom-color: var(--primary);
}

.create-eula__notice {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
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

/* Scope-migrated from global.css in Phase 7 Task 7
   (sole remaining caller after FormField migration). */
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
.form-group select {
  width: 100%;
}

.form-hint {
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

.form-checkboxes {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.625rem;
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

@media (max-width: 768px) {
  .form-row,
  .form-checkboxes {
    grid-template-columns: 1fr;
  }
}

/* Phase 3c: install-progress UI panes shown after the user submits and the
   backend returns 202. The form is hidden during this state. */
.install-progress-pane,
.install-failed-pane {
  padding: 24px 16px;
  text-align: center;
}

.install-progress-phase {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 8px 0 16px;
}

.install-progress-bar-wrap {
  position: relative;
  height: 20px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
  margin: 16px auto;
  max-width: 320px;
}

.install-progress-bar-fill {
  height: 100%;
  background: var(--primary);
  transition: width 200ms ease-out;
}

.install-progress-bytes {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.install-progress-spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--bg-tertiary);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: install-spin 0.8s linear infinite;
  margin: 16px auto;
}

@keyframes install-spin {
  to { transform: rotate(360deg); }
}

.install-progress-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 16px auto;
  max-width: 360px;
}

.install-progress-actions,
.install-failed-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}

.install-failed-error {
  color: var(--danger);
  margin: 8px 0 16px;
  white-space: pre-wrap;
}
</style>
