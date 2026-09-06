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
      <!-- First question, not a later one. A modpack targets a specific
           Minecraft version and loader, so when one is being imported it is the
           pack that decides those — picking them first and discovering the pack
           wanted something else is the wrong way round. -->
      <div class="mode-toggle" role="tablist" aria-label="Server setup mode">
        <button
          type="button"
          role="tab"
          class="mode-toggle-btn"
          :class="{ active: formData.setupMode === 'custom' }"
          :aria-selected="formData.setupMode === 'custom'"
          @click="formData.setupMode = 'custom'"
        >
          Custom Server
        </button>
        <button
          type="button"
          role="tab"
          class="mode-toggle-btn"
          :class="{ active: formData.setupMode === 'modpack' }"
          :aria-selected="formData.setupMode === 'modpack'"
          @click="formData.setupMode = 'modpack'"
        >
          Import Modpack
        </button>
      </div>

      <!-- Above Basic Settings on purpose: the pack decides the Minecraft
           version and loader shown there, so it has to be chosen first. -->
      <Panel v-if="showModpackPanel" title="Modpack Setup">

        <p class="form-hint">
          Choose a Modrinth pack by link, by search, or by uploading a .mrpack
          file you exported yourself. The Minecraft version and loader in Basic
          Settings are filled in from the pack.
        </p>

        <div class="modpack-panel">
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
                    @keydown.enter.prevent="!modpackLookupLoading && modpackLinkInput.trim() && resolveModpackByLink()"
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

          <div v-else-if="formData.modpackImportMethod === 'search'" class="modpack-search-branch">
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
                      @keydown.enter.prevent="!modpackSearchLoading && modpackSearchQuery.trim() && searchForModpacks()"
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

            <!-- Heading and list grouped so the panel's 16px gap separates this
                 block from its neighbours, while the label stays tight to the
                 list it names. -->
            <div v-if="modpackSearchResults.length && !selectedModpack" class="modpack-results-block">
              <p
                v-if="modpackShowingPopular && !modpackSearchLoading"
                class="modpack-results-heading"
              >
                Popular on Modrinth — or search above
              </p>

              <div class="modpack-results">
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
            </div>

            <p v-if="modpackSearchDone && !modpackSearchLoading && !modpackSearchResults.length" class="form-hint">
              <template v-if="modpackShowingPopular">Could not load modpacks right now. Try searching by name.</template>
              <template v-else>No matching modpacks found for this search.</template>
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
            <img
              v-if="selectedModpack.iconUrl"
              :src="selectedModpack.iconUrl"
              alt=""
              class="modpack-icon"
            >
            <div class="modpack-selected__text">
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
                  v-for="loaderOption in availableLoaderOptions"
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
      // Same idea, but for a search/link-resolved pack: it declares a whole
      // list of supported versions rather than one exact build, so the newest
      // one the target loader actually has is picked once that list loads.
      pendingPackVersions: [],
      // Version + loader as they stood before a pack overwrote them, so
      // clearing the pack puts the form back rather than leaving the pack's
      // choices behind as if the user had made them. Null when no pack has
      // applied its defaults.
      prePackSelection: null,
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
        // Search first: browsing by name is how most people arrive at a
        // pack. A link or slug assumes you already have one in hand.
        modpackImportMethod: 'search',
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
    // No mcVersion/loader getters: unlike ModpackBrowserModal (installing onto
    // a real server that's already pinned to a version and loader), nothing is
    // chosen yet at creation time — search must return every pack regardless
    // of formData.version's default, or packs get silently filtered out
    // before the user has picked one. The pack itself decides the loader and
    // version once chosen — see applySearchPackDefaults.
    this.imp = useModpackImport()
    this.loadGameVersions()
  },
  computed: {
    showModpackPanel() {
      // Driven by the mode tab, not by the loader. Gating this on the loader
      // was the inversion: the panel is where the loader gets decided (a pack
      // declares the version and loader build it was assembled against), so
      // requiring a loader first made it unreachable until after the choice it
      // was supposed to be making. Picking a non-mod loader by hand still
      // returns to Custom — see the formData.loader watcher.
      return this.formData.setupMode === 'modpack'
    },
    filteredGameVersions() {
      const pool = this.compatibleGameVersions || this.gameVersions
      if (this.showSnapshots) return pool
      return pool.filter(v => v.stable)
    },
    // Once a search/link-resolved pack is chosen, narrow the version select to
    // builds the pack actually declares support for — but only if that leaves
    // something to pick. An empty intersection means Modrinth's list and this
    // loader's list didn't overlap at all, which packMismatchWarning already
    // surfaces; falling back to the full list there keeps the field usable
    // instead of showing an empty, disabled select.
    compatibleGameVersions() {
      if (this.formData.setupMode !== 'modpack' || !this.selectedModpack?.gameVersions?.length) {
        return null
      }
      const allowed = this.selectedModpack.gameVersions
      const matches = this.gameVersions.filter(v => allowed.includes(v.version))
      return matches.length ? matches : null
    },
    // Same narrowing for the loader select, with the same empty-intersection
    // fallback (also covered by the "Unsupported Loader" toast elsewhere).
    compatibleLoaderOptions() {
      if (this.formData.setupMode !== 'modpack' || !this.selectedModpack?.loaders?.length) {
        return null
      }
      const allowed = this.selectedModpack.loaders
      const matches = this.loaderOptions.filter(option => allowed.includes(option.value))
      return matches.length ? matches : null
    },
    availableLoaderOptions() {
      return this.compatibleLoaderOptions || this.loaderOptions
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
    modpackShowingPopular() {
      return this.imp?.showingPopular ?? false
    },
    modpackLookupLoading() {
      return this.imp?.resolving ?? false
    },
    modpackSearchLoading() {
      return this.imp?.loading ?? false
    },
    modpackError: {
      // These two read and write the unwrapped ref, like every other accessor
      // here. Reaching through `.value` returned undefined off a plain string,
      // so modpack errors were resolving to '' and never rendering.
      get() { return this.imp?.errorMessage ?? '' },
      set(v) { if (this.imp) this.imp.errorMessage = v }
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
      // The version and loader stay editable after a pack is chosen, so say
      // plainly when they have drifted from what the pack supports. Creating
      // anyway is allowed — only the user knows whether a pack is portable.
      //
      // Both sources are covered. An uploaded .mrpack declares exactly one
      // version and loader. A pack chosen from search carries the lists
      // Modrinth publishes, so "supported" there means "in the list" rather
      // than "equal to". Without this, a search pack's only feedback was the
      // create request failing, after the whole form had been filled in.
      const differences = []

      if (this.uploadedPack) {
        const packMc = this.uploadedPack.minecraft_version || ''
        const packLoader = (this.uploadedPack.loader || '').toLowerCase()
        if (packMc && this.formData.version && packMc !== this.formData.version) {
          differences.push(`Minecraft ${packMc}`)
        }
        if (packLoader && this.formData.loader && packLoader !== this.formData.loader) {
          differences.push(this.loaderLabelFor(packLoader))
        }
      } else if (this.selectedModpack) {
        const versions = this.selectedModpack.gameVersions || []
        const loaders = this.selectedModpack.loaders || []
        // An empty list means Modrinth told us nothing, which is not the same
        // as "incompatible" — stay quiet rather than warn on missing data.
        if (versions.length && this.formData.version && !versions.includes(this.formData.version)) {
          differences.push(`Minecraft ${this.packSupportSummary(versions)}`)
        }
        if (loaders.length && this.formData.loader && !loaders.includes(this.formData.loader)) {
          differences.push(loaders.map((value) => this.loaderLabelFor(value)).join(' or '))
        }
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
      if (method === 'search') this.loadPopularModpacks()
    },
    // Deleting the text back to empty by hand has no button to press
    // afterward — Search disables itself with nothing typed, and pressing
    // Enter on an empty box is a no-op too — so the previous query's results
    // would otherwise just sit there with no way back. Falls back to the same
    // popular list shown before anything was ever typed. Guarded to the
    // modpack/search view so resetForm()'s resetAll() (which also clears this
    // to '') doesn't fire an unwanted fetch while the modal is closing.
    modpackSearchQuery(newQuery) {
      if (
        !newQuery.trim() &&
        this.formData.setupMode === 'modpack' &&
        this.formData.modpackImportMethod === 'search'
      ) {
        this.imp.loadPopular()
      }
    },
    'formData.setupMode'(mode) {
      if (mode === 'modpack') {
        // Entering the modpack flow with Search selected (the default) should
        // land on a list, not an empty box.
        if (this.formData.modpackImportMethod === 'search') this.loadPopularModpacks()
        return
      }
      // Leaving it: drop the pack rather than keeping it staged out of sight.
      // buildModpackIntent() returns null outside modpack mode, so a pack left
      // selected here was silently not installed — the user picked one, saw it
      // still listed on the tab they came from, and got a bare server. An
      // uploaded archive also has to be discarded, not just forgotten, and
      // clearing restores the version and loader the pack overwrote.
      this.clearSelectedModpack()
      this.clearUploadedPack()
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
        // The stash is dropped, not restored: the user just chose this loader
        // by hand, and that outranks both the pack's defaults and whatever
        // preceded them. Cleared first so the restore inside
        // clearSelectedModpack is a no-op and cannot undo that choice.
        this.prePackSelection = null
        // Via the composable rather than assigning through `.value`: the ref is
        // unwrapped in data(), so the old form set a `value` key on the pack
        // object and left the selection in place.
        this.clearSelectedModpack()
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

    async resolveModpackByLink() {
      await this.imp.resolveByLink()
      // A 404'd link falls back to search results instead of a selection —
      // nothing to apply defaults from in that case.
      if (this.selectedModpack) {
        await this.applySearchPackDefaults(this.selectedModpack)
      }
    },

    searchForModpacks() {
      // Releases the lock: with a pack selected the results list is hidden, so
      // a search that left the selection in place would look like it did
      // nothing. Clear is the other way back.
      this.clearSelectedModpack()
      return this.imp.performSearch()
    },

    /** Fill the search view with top-downloaded packs so it never opens blank.
     *
     * Unfiltered on purpose: this is the pack-first flow, so no Minecraft
     * version or loader has been chosen yet — the pack is what decides them.
     * Skipped when results are already on screen so switching import method
     * back and forth does not re-request the same list.
     */
    loadPopularModpacks() {
      // No `.value`: `imp` is stored in data(), so reactive() has already
      // unwrapped its refs — same convention as the computeds above.
      if (!this.imp || this.imp.loading || this.modpackSearchResults.length) return
      return this.imp.loadPopular()
    },

    async selectModpackFromSearch(pack) {
      this.imp.selectPack(pack)
      await this.applySearchPackDefaults(this.selectedModpack)
    },

    clearSelectedModpack() {
      this.imp.clearSelection()
      this.pendingPackVersions = []
      this.restorePrePackSelection()
    },

    /** Fill the loader and Minecraft version in from a search/link-resolved
     * pack: unlike an uploaded .mrpack (one declared build), Modrinth gives a
     * whole list of supported versions and loaders, so the newest version the
     * chosen loader actually has is picked. Both stay editable afterward. */
    async applySearchPackDefaults(pack) {
      if (!pack) return

      // Recorded once per run, same as the upload path: swapping one pack for
      // another must still restore what the user had before any pack was
      // involved.
      if (!this.prePackSelection) {
        this.prePackSelection = {
          version: this.formData.version,
          loader: this.formData.loader,
        }
      }

      const supportedLoaders = (pack.loaders || []).filter(
        (value) => this.loaderOptions.some((option) => option.value === value)
      )
      this.pendingPackVersions = pack.gameVersions || []

      if (!supportedLoaders.length) {
        this.toast.warning(
          `This pack's loader isn't one Fabricator can install. Pick a loader yourself.`,
          'Unsupported Loader',
        )
        // Still worth trying a compatible version against whatever loader is
        // already set, rather than leaving the version untouched too.
        await this.applyPendingPackVersion()
        await this.refreshJavaRequirement()
        return
      }

      // Keep the current loader if the pack already supports it — otherwise
      // take the first one Modrinth lists, which is normally the pack's
      // primary loader.
      const targetLoader = supportedLoaders.includes(this.formData.loader)
        ? this.formData.loader
        : supportedLoaders[0]

      if (targetLoader !== this.formData.loader) {
        // The loader watcher calls loadGameVersions(), which resolves the
        // pending version list once that loader's builds are in — mirrors
        // applyPackDefaults below for uploaded packs.
        this.formData.loader = targetLoader
        return
      }

      // Loader already matches, so the watcher above won't fire — resolve now.
      await this.applyPendingPackVersion()
      await this.refreshJavaRequirement()
    },

    /** A readable "1.21.1, 1.20.1 or 3 others" for a pack's version list.
     *
     * Popular packs support a dozen versions; naming them all would bury the
     * point of the warning, which is that the chosen one is not among them.
     */
    packSupportSummary(versions) {
      const named = versions.slice(0, 3).join(', ')
      const rest = versions.length - 3
      if (rest <= 0) return named
      return `${named} or ${rest} other${rest === 1 ? '' : 's'}`
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

      // Recorded once per run: swapping one pack for another must still
      // restore what the user had before any pack was involved.
      if (!this.prePackSelection) {
        this.prePackSelection = {
          version: this.formData.version,
          loader: this.formData.loader,
        }
      }

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
      // Search/link pack: a whole list of supported versions rather than one
      // exact build. gameVersions is already newest-first (loadGameVersions
      // picks its [0] as "preferred"), so the first entry present in both is
      // the newest one this loader actually has.
      if (this.pendingPackVersions.length) {
        const wanted = this.pendingPackVersions
        this.pendingPackVersions = []

        const candidates = this.gameVersions.filter(v => wanted.includes(v.version))
        const match = candidates.find(v => v.stable) || candidates[0]
        if (!match) {
          this.toast.warning(
            `This pack has no build for the Minecraft versions this loader supports. Pick a version yourself.`,
            'Version Unavailable',
          )
          return
        }
        if (!match.stable) {
          this.showSnapshots = true
        }
        this.formData.version = match.version
        return
      }

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

    /** Put version + loader back to their pre-pack values, if a pack set them. */
    restorePrePackSelection() {
      const previous = this.prePackSelection
      this.prePackSelection = null
      if (!previous) return
      // Drop a pack version that never got applied, so a pending one cannot
      // land on top of the restore once the version list reloads.
      this.pendingPackVersion = ''
      this.pendingPackVersions = []
      // Version first: changing the loader triggers loadGameVersions, which
      // keeps the current version when the incoming loader offers it. Setting
      // it afterwards would race that reload instead.
      this.formData.version = previous.version
      this.formData.loader = previous.loader
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
        // keepInput means one upload is replacing another, and the incoming
        // pack is about to set these again — restoring in between would just
        // flicker the version select.
        this.restorePrePackSelection()
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
          if (previousVersion && previousVersion !== preferred.version && !this.pendingPackVersion && !this.pendingPackVersions.length) {
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
      // Nothing to restore into a form that is being rebuilt from scratch.
      this.prePackSelection = null
      this.formData = {
        setupMode: 'custom',
        modpackImportMethod: 'search',
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

/* Panel lays its body out as a plain block, and global.css zeroes every
   margin — so stacked fields inside one panel had NO space between them at
   all: the previous field's input sat flush against the next field's label,
   and a field's hint ran straight into the heading under it. Matching the
   grid's own 20px column gap gives the same rhythm down as across.
   Scoped here rather than in Panel: other views place their own spacing
   inside panel bodies, and a global gap would double it. */
.settings-form :deep(.panel__body) {
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
  /* Shrink-to-fit: as a flex item of the form column it would otherwise stretch
     to the full width and stop reading as a pair of pills. */
  align-self: flex-start;
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

/* Top-aligned, not bottom. The `&nbsp;` label in the action column reserves the
   label row so the button's top lines up with the input's; bottom-aligning
   instead measured the whole column, so on the Link row — whose field carries a
   hint underneath — the button was pushed a hint's height below the input it
   belongs to, while the hintless Search row looked fine. */
/* The rows inside this branch are siblings in a plain block, so without this
   the results heading sat flush against the search field. */
.modpack-search-branch {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Ghost buttons default to --bg-tertiary, which is exactly the panel's own
   background — inside here they were an invisible rectangle with a border one
   shade off the surface, and half that at disabled opacity. Drop them onto the
   darker base the inputs use so they read as controls. */
.modpack-panel :deep(.app-btn--ghost) {
  background: var(--bg-primary);
  border-color: #2a2a2a;
  color: var(--text-secondary);
}

.modpack-panel :deep(.app-btn--ghost:hover:not(:disabled)) {
  border-color: var(--primary);
  color: var(--primary);
}

/* Compound with .form-row: a bare `.modpack-input-row` selector has the same
   specificity as `.form-row` below, so — since `.form-row` is declared later
   in this file — its `1fr 1fr` was winning the cascade and silently undoing
   this override, which is what actually gave a single button half the width. */
.form-row.modpack-input-row {
  align-items: start;
  grid-template-columns: minmax(0, 1fr) auto;
}

.modpack-grow {
  flex: 1;
}

.modpack-action {
  min-width: 110px;
}

/* Takes the free space so Clear stays hard right, and lets a long title
   ellipsise rather than push the button off the card. */
.modpack-selected__text {
  flex: 1;
  min-width: 0;
}

.modpack-selected__text strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modpack-results-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* Labels the top-downloads list so it is not read as matches to a query. */
.modpack-results-heading {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
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

/* The text column is a flex item, so it needs min-width: 0 of its own — the
   default `auto` refuses to shrink below its content, which let a long pack
   title push the download count off the row instead of ellipsising. */
.modpack-result-header > div {
  min-width: 0;
}

.modpack-result-header strong {
  display: block;
  color: var(--text-primary);
  font-size: var(--text-sm);
  /* Block, so the truncation below applies: <strong> is inline by default and
     overflow has no effect on it. */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* Three across now: icon, text, Clear. align-items:center so the icon and the
   button sit level with the text block rather than pinned to its first line. */
.modpack-selected {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: center;
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
/* These hand-rolled equivalents of FormField sit directly beside real ones —
   "Minecraft Version" shares a row with "Mod Loader" — so their type has to be
   the same or the row looks subtly broken. The raw rem values had drifted off
   the scale: labels were 14px against FormField's 13px, and hints 13px against
   its 11px, which made the same kind of text two different sizes in one form. */
.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.form-group label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

.form-group input,
.form-group select {
  width: 100%;
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}

.form-checkboxes {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
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
