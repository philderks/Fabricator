<template>
  <BaseModal
    :show="show"
    title="Browse Modpacks"
    size="xlarge"
    @close="$emit('close')"
  >
    <div class="search-section">
      <div class="filter-chip">
        Filtered to Minecraft {{ mcVersion }} ({{ loaderLabel }})
      </div>

      <div class="import-method">
        <label class="choice-pill">
          <input type="radio" v-model="importMethod" value="search">
          <span>Search</span>
        </label>
        <label class="choice-pill">
          <input type="radio" v-model="importMethod" value="link">
          <span>Link</span>
        </label>
        <label class="choice-pill">
          <input type="radio" v-model="importMethod" value="file">
          <span>Upload .mrpack</span>
        </label>
      </div>

      <div v-if="importMethod === 'file'" class="upload-row">
        <input
          ref="fileInput"
          type="file"
          accept=".mrpack,application/zip"
          :disabled="uploading"
          @change="handleFileChange"
        >
        <p v-if="uploading" class="upload-status">
          {{ uploadPercent >= 0 ? `Uploading ${uploadPercent}%` : 'Uploading…' }}
        </p>
        <div v-else-if="uploadedPack" class="uploaded-pack">
          <div>
            <strong>{{ uploadedPackTitle }}</strong>
            <p>{{ uploadedPackDetail }}</p>
          </div>
          <AppButton variant="ghost" size="sm" @click="clearUploadedPack">Clear</AppButton>
        </div>
        <p v-if="mismatchWarning" class="warning-text">{{ mismatchWarning }}</p>
        <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
      </div>

      <div v-else-if="importMethod === 'search'" class="search-row">
        <div class="search-bar">
          <input
            v-model="imp.searchQuery.value"
            type="text"
            placeholder="Search modpacks..."
            @keyup.enter="imp.performSearch()"
          >
        </div>
        <AppButton
          variant="ghost"
          size="md"
          :disabled="imp.loading.value || !imp.searchQuery.value.trim()"
          @click="imp.performSearch()"
        >
          {{ imp.loading.value ? 'Searching...' : 'Search' }}
        </AppButton>
      </div>

      <div v-else class="search-row">
        <div class="search-bar">
          <input
            v-model="imp.modpackLink.value"
            type="text"
            placeholder="https://modrinth.com/modpack/... or slug"
            @keyup.enter="imp.resolveByLink()"
          >
        </div>
        <AppButton
          variant="ghost"
          size="md"
          :disabled="imp.resolving.value || !imp.modpackLink.value.trim()"
          @click="imp.resolveByLink()"
        >
          {{ imp.resolving.value ? 'Resolving...' : 'Resolve' }}
        </AppButton>
      </div>

      <p v-if="imp.errorMessage.value" class="error-text">{{ imp.errorMessage.value }}</p>
    </div>

    <div v-if="imp.loading.value" class="loading-state">
      <div class="spinner"></div>
      <p>Searching modpacks...</p>
    </div>

    <div v-else-if="imp.searchResults.value.length" class="results-grid">
      <SearchResultCard
        v-for="pack in imp.searchResults.value"
        :key="pack.project_id || pack.id"
        :icon-url="pack.icon_url || pack.iconUrl || null"
        :title="pack.title || pack.name || pack.slug"
        :description="truncate(pack.description, 120)"
        :meta="formatModpackMeta(pack)"
        :selected="imp.selectedModpack.value && imp.selectedModpack.value.id === (pack.project_id || pack.id)"
        @click="handleSelectPack(pack)"
      >
        <AppButton
          variant="primary"
          size="sm"
          @click.stop="handleInstallPack(pack)"
        >
          Install
        </AppButton>
      </SearchResultCard>
    </div>

    <div v-else class="modpack-browser-empty">
      <svg class="modpack-browser-empty__icon" width="64" height="64" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M9 9H15M9 13H13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h3 class="modpack-browser-empty__heading" v-if="importMethod === 'file'">Upload a modpack file</h3>
      <h3 class="modpack-browser-empty__heading" v-else-if="importMethod === 'search' && imp.searchDone.value">No modpacks found</h3>
      <h3 class="modpack-browser-empty__heading" v-else-if="importMethod === 'search'">Search for modpacks</h3>
      <h3 class="modpack-browser-empty__heading" v-else>Resolve a modpack link</h3>
      <p class="modpack-browser-empty__body" v-if="importMethod === 'file'">
        Pick a .mrpack exported from the Modrinth app. Its mods are fetched from Modrinth; config and other extras come from the pack's overrides.
      </p>
      <p class="modpack-browser-empty__body" v-else-if="importMethod === 'search' && imp.searchDone.value">
        No modpacks found for "{{ imp.searchQuery.value }}" on {{ loaderLabel }} {{ mcVersion }}. Try different keywords or check that your server's MC version has compatible modpacks.
      </p>
      <p class="modpack-browser-empty__body" v-else-if="importMethod === 'search'">
        Search for modpacks compatible with {{ mcVersion }}.
      </p>
      <p class="modpack-browser-empty__body" v-else>
        Paste a Modrinth modpack link or slug to resolve it.
      </p>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" @click="$emit('close')">Close</AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="!canInstall"
        @click="confirmInstall"
      >
        Install Selected Modpack
      </AppButton>
    </template>
  </BaseModal>
</template>

<script setup>
// Q: structural lookalike to ModBrowserModal (search-bar → results-grid →
// empty-state → footer + matching prop shape `show`/`mcVersion`/`loader`).
// formatNumber + truncate already share `utils/format.js` (F4). A full
// `useResourceBrowser` composable extraction is EXCLUDED (H3 cluster /
// CC7 Setup-API migration); track in FINDINGS.md if revisited.
import { ref, computed, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import SearchResultCard from '../ui/SearchResultCard.vue'
import AppButton from '../ui/AppButton.vue'
import { useModpackImport } from '../../composables/useModpackImport'
import { uploadModpackArchive, discardModpackUpload } from '../../api/modrinth'
import { formatNumber, truncate } from '../../utils/format'

const props = defineProps({
  show: { type: Boolean, required: true },
  mcVersion: { type: String, default: '' },
  loader: { type: String, default: 'fabric' },
})

const emit = defineEmits(['close', 'install'])

const importMethod = ref('search')
const fileInput = ref(null)
const uploadedPack = ref(null)
const uploading = ref(false)
const uploadPercent = ref(0)
const uploadError = ref('')
// Not reactive: nothing renders it, it only needs to survive between calls.
let abortUpload = null

const loaderLabel = computed(() => {
  const value = (props.loader || 'fabric').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
})

const imp = useModpackImport({
  mcVersion: () => props.mcVersion,
  loader: () => props.loader
})

const uploadedPackTitle = computed(
  () => uploadedPack.value?.name || uploadedPack.value?.filename || 'Uploaded modpack'
)

const uploadedPackDetail = computed(() => {
  const pack = uploadedPack.value
  if (!pack) return ''
  const parts = []
  if (pack.version) parts.push(`Version ${pack.version}`)
  if (pack.minecraft_version) parts.push(`Minecraft ${pack.minecraft_version}`)
  if (pack.loader) parts.push(pack.loader)
  if (pack.file_count) parts.push(`${pack.file_count} file${pack.file_count === 1 ? '' : 's'}`)
  return parts.join(' · ')
})

// An uploaded pack states what it was built for; this server is already fixed
// on a version and loader, so say plainly when the two disagree rather than
// letting the install produce a server that will not boot. It stays a warning:
// only the user knows whether the pack happens to be portable.
const mismatchWarning = computed(() => {
  const pack = uploadedPack.value
  if (!pack) return ''
  const differences = []
  const serverLoader = (props.loader || '').toLowerCase()
  const packLoader = (pack.loader || '').toLowerCase()
  if (pack.minecraft_version && props.mcVersion && pack.minecraft_version !== props.mcVersion) {
    differences.push(`Minecraft ${pack.minecraft_version}`)
  }
  if (packLoader && serverLoader && packLoader !== serverLoader) {
    differences.push(packLoader)
  }
  if (!differences.length) return ''
  return `This pack was built for ${differences.join(' and ')}, but this server runs ${loaderLabel.value} ${props.mcVersion}. Installing it anyway may leave the server unable to start.`
})

const canInstall = computed(() =>
  importMethod.value === 'file' ? Boolean(uploadedPack.value) : Boolean(imp.selectedModpack.value)
)

watch(() => props.show, (next) => {
  if (!next) {
    importMethod.value = 'search'
    imp.resetAll()
    clearUploadedPack()
  }
})

watch(importMethod, (next) => {
  // The two halves answer the same question; leaving both populated would
  // make the footer button's target ambiguous.
  if (next === 'file') {
    imp.resetAll()
  } else {
    clearUploadedPack()
  }
})

async function handleFileChange(event) {
  const file = event?.target?.files?.[0]
  if (!file) return

  await clearUploadedPack({ keepInput: true })
  uploading.value = true
  uploadPercent.value = 0
  uploadError.value = ''
  try {
    uploadedPack.value = await uploadModpackArchive(file, {
      onProgress: (pct) => { uploadPercent.value = pct },
      registerAbort: (abort) => { abortUpload = abort }
    })
  } catch (error) {
    if (fileInput.value) fileInput.value.value = ''
    // Cancelling is something the user just did (closed the modal, picked a
    // different file); only a real failure is worth reporting.
    if (error?.message !== 'Upload cancelled') {
      uploadError.value = error?.message || 'Could not read that .mrpack file.'
    }
  } finally {
    uploading.value = false
    abortUpload = null
  }
}

async function clearUploadedPack({ keepInput = false } = {}) {
  if (abortUpload) {
    // Stops an in-flight upload from staging an archive nobody will install.
    abortUpload()
    abortUpload = null
  }
  const pack = uploadedPack.value
  uploadedPack.value = null
  uploadError.value = ''
  uploadPercent.value = 0
  if (!keepInput && fileInput.value) {
    fileInput.value.value = ''
  }
  if (pack?.upload_id) {
    // Best effort: a staged pack expires on its own, so a failed discard is
    // not worth putting in front of the user.
    try {
      await discardModpackUpload(pack.upload_id)
    } catch (_) {
      // ignore
    }
  }
}

function handleSelectPack(pack) {
  imp.selectPack(pack)
}

function handleInstallPack(pack) {
  imp.selectPack(pack)
  confirmInstall()
}

function confirmInstall() {
  if (importMethod.value === 'file') {
    if (!uploadedPack.value) {
      return
    }
    emit('install', {
      uploadId: uploadedPack.value.upload_id,
      title: uploadedPackTitle.value,
      mcVersion: props.mcVersion,
      loader: (props.loader || 'fabric').toLowerCase(),
      // The mismatch has already been shown above the Install button, so the
      // backend's own 409 would only repeat a question that was answered.
      force: true,
    })
    uploadedPack.value = null
    if (fileInput.value) fileInput.value.value = ''
    return
  }
  if (!imp.selectedModpack.value) {
    return
  }
  emit('install', {
    projectId: imp.selectedModpack.value.id,
    title: imp.selectedModpack.value.title,
    mcVersion: props.mcVersion,
    loader: (props.loader || 'fabric').toLowerCase(),
  })
}


// Modrinth tags loader compatibility as ordinary categories ('fabric',
// 'forge', 'neoforge', 'quilt'). Multi-loader packs are tagged with all
// four, so the alphabetical first three would read "fabric, forge, …" —
// regardless of which loader the user is actually browsing for, leaving
// the impression that the search is dominated by Fabric packs. Strip
// loader tags here; the active loader is already shown in the filter chip.
const LOADER_TAGS = new Set(['fabric', 'forge', 'neoforge', 'quilt'])

function formatModpackMeta(pack) {
  const parts = []
  if (pack.downloads) parts.push(`${formatNumber(pack.downloads)} downloads`)
  if (pack.categories && pack.categories.length) {
    const nonLoader = pack.categories.filter((c) => !LOADER_TAGS.has(String(c).toLowerCase()))
    if (nonLoader.length) {
      parts.push(nonLoader.slice(0, 3).join(', '))
    }
  }
  return parts.join(' · ')
}
</script>

<style scoped>
.search-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.filter-chip {
  align-self: flex-start;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.import-method {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.choice-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  cursor: pointer;
}

.search-row {
  display: flex;
  gap: var(--space-3);
}

.search-bar {
  flex: 1;
}

.search-bar input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: border-color 0.15s ease;
}

.search-bar input:focus {
  outline: none;
  border-color: var(--primary);
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
  animation: modpack-browser-spin 0.8s linear infinite;
}

@keyframes modpack-browser-spin {
  to {
    transform: rotate(360deg);
  }
}

.results-grid {
  display: grid;
  gap: var(--space-3);
  max-height: 500px;
  overflow-y: auto;
  padding: var(--space-1);
}

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

.modpack-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-10) 0;
  color: var(--text-muted);
  text-align: center;
}

.modpack-browser-empty__icon {
  color: var(--text-disabled);
}

.modpack-browser-empty__heading {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-secondary);
  line-height: var(--leading-tight);
}

.modpack-browser-empty__body {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.error-text {
  margin: 0;
  color: var(--danger);
  font-size: var(--text-sm);
}

.upload-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.upload-row input[type="file"] {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.upload-row input[type="file"]:disabled {
  opacity: 0.6;
  cursor: progress;
}

.upload-status {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.uploaded-pack {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: color-mix(in oklch, var(--success) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--success) 28%, transparent);
}

.uploaded-pack strong {
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.uploaded-pack p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.warning-text {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--warning) 28%, transparent);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 768px) {
  .search-row {
    flex-direction: column;
  }
}
</style>
