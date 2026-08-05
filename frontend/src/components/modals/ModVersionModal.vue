<script setup>
/**
 * Pick a specific Modrinth version to install (#56).
 *
 * Two entry points, one component: choosing a version at install time from the
 * mod browser, and changing the version of a mod already on disk. The only
 * difference is `installedVersionId`, which marks the current row and switches
 * the button copy from "Install" to "Switch to this version".
 *
 * Versions are listed unfiltered by game version on purpose. Pinning an older
 * build for compatibility is the whole point of the feature, and such a build
 * often predates the server's Minecraft version — filtering it out would hide
 * exactly what the user came for. Instead every row states its compatibility,
 * and anything that does not target this server is marked before it is chosen.
 */
import { computed, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { getModVersions } from '../../api/modrinth'

const props = defineProps({
  show: { type: Boolean, required: true },
  /** Modrinth project id or slug. */
  projectId: { type: String, default: '' },
  projectTitle: { type: String, default: '' },
  /** The server's Minecraft version, used to flag compatibility per row. */
  mcVersion: { type: String, default: '' },
  /** Loader facets this server accepts (e.g. ['paper','spigot','bukkit']). */
  loaders: { type: Array, default: () => [] },
  /** Version currently on disk, if any — marks the row and retitles the CTA. */
  installedVersionId: { type: String, default: '' }
})

const emit = defineEmits(['close', 'select'])

const versions = ref([])
const loading = ref(false)
const error = ref('')
const selectedId = ref('')
const showIncompatible = ref(false)

const TYPE_LABELS = { release: 'Release', beta: 'Beta', alpha: 'Alpha' }

function targetsThisServer(version) {
  if (!props.mcVersion) return true
  const games = Array.isArray(version.game_versions) ? version.game_versions : []
  return games.includes(props.mcVersion)
}

const decorated = computed(() =>
  versions.value.map((v) => ({
    id: v.id,
    number: v.version_number || v.id,
    name: v.name || '',
    type: TYPE_LABELS[v.version_type] || v.version_type || '',
    published: v.date_published ? new Date(v.date_published).toLocaleDateString() : '',
    games: Array.isArray(v.game_versions) ? v.game_versions : [],
    loaders: Array.isArray(v.loaders) ? v.loaders : [],
    compatible: targetsThisServer(v),
    installed: Boolean(props.installedVersionId) && v.id === props.installedVersionId
  }))
)

const compatibleCount = computed(() => decorated.value.filter((v) => v.compatible).length)

// Incompatible builds stay collapsed until asked for: they are the minority
// case, and a list that opens on 200 irrelevant rows buries the useful ones.
const visible = computed(() =>
  showIncompatible.value ? decorated.value : decorated.value.filter((v) => v.compatible)
)

const selected = computed(() => decorated.value.find((v) => v.id === selectedId.value) || null)

const confirmLabel = computed(() => {
  if (!props.installedVersionId) return 'Install this version'
  return selected.value?.installed ? 'Reinstall this version' : 'Switch to this version'
})

async function load() {
  if (!props.projectId) return
  loading.value = true
  error.value = ''
  versions.value = []
  selectedId.value = ''
  showIncompatible.value = false
  try {
    // Loader is filtered server-side; game version deliberately is not (see
    // the component docblock).
    const filters = {}
    if (props.loaders.length) filters.loaders = props.loaders
    const result = await getModVersions(props.projectId, filters)
    versions.value = Array.isArray(result) ? result : []
    // Preselect what is installed, else the newest compatible build, so the
    // common case is one click.
    const installed = decorated.value.find((v) => v.installed)
    selectedId.value = installed?.id || decorated.value.find((v) => v.compatible)?.id || ''
    if (!compatibleCount.value && decorated.value.length) showIncompatible.value = true
  } catch (err) {
    error.value = err?.message || 'Could not load versions for this mod.'
  } finally {
    loading.value = false
  }
}

watch(() => [props.show, props.projectId], ([show]) => { if (show) load() }, { immediate: true })

function confirm() {
  if (!selected.value) return
  emit('select', {
    versionId: selected.value.id,
    versionNumber: selected.value.number,
    compatible: selected.value.compatible
  })
}
</script>

<template>
  <BaseModal
    :show="show"
    :title="projectTitle ? `Versions — ${projectTitle}` : 'Choose a version'"
    size="large"
    @close="emit('close')"
  >
    <p v-if="loading" class="mv__state">Loading versions…</p>
    <p v-else-if="error" class="mv__state mv__state--error" role="alert">{{ error }}</p>
    <p v-else-if="!decorated.length" class="mv__state">No versions published for this loader.</p>

    <template v-else>
      <p class="mv__lead">
        <template v-if="compatibleCount">
          Showing versions for Minecraft {{ mcVersion }}.
        </template>
        <template v-else>
          No version targets Minecraft {{ mcVersion }} — everything below is for another version.
        </template>
      </p>

      <ul class="mv__list">
        <li v-for="version in visible" :key="version.id">
          <label class="mv__row" :class="{ 'mv__row--selected': version.id === selectedId }">
            <input
              type="radio"
              class="mv__radio"
              :value="version.id"
              :checked="version.id === selectedId"
              @change="selectedId = version.id"
            />
            <span class="mv__main">
              <span class="mv__number">
                {{ version.number }}
                <span v-if="version.installed" class="mv__badge mv__badge--installed">Installed</span>
                <span v-if="version.type" class="mv__badge">{{ version.type }}</span>
                <span v-if="!version.compatible" class="mv__badge mv__badge--warn">
                  Not for {{ mcVersion }}
                </span>
              </span>
              <span class="mv__meta">
                {{ version.published }}
                <template v-if="version.games.length"> · MC {{ version.games.join(', ') }}</template>
              </span>
            </span>
          </label>
        </li>
      </ul>

      <button
        v-if="compatibleCount && compatibleCount < decorated.length"
        type="button"
        class="mv__toggle"
        @click="showIncompatible = !showIncompatible"
      >
        {{ showIncompatible
          ? 'Hide versions for other Minecraft versions'
          : `Show ${decorated.length - compatibleCount} version(s) for other Minecraft versions` }}
      </button>

      <p v-if="selected && !selected.compatible" class="mv__warn" role="status">
        This build does not list Minecraft {{ mcVersion }}. Installing it is allowed — that is
        often deliberate — but the mod may fail to load.
      </p>
    </template>

    <template #footer>
      <AppButton variant="ghost" @click="emit('close')">Cancel</AppButton>
      <AppButton variant="primary" :disabled="!selected || loading" @click="confirm">
        {{ confirmLabel }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.mv__state {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
}
.mv__state--error { color: var(--danger); }

.mv__lead {
  margin: 0 0 var(--space-3);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.mv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-height: 46vh;
  overflow-y: auto;
}

.mv__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.mv__row:hover { border-color: var(--border-hover); }
.mv__row--selected {
  border-color: var(--primary);
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.mv__radio { margin-top: 0.2rem; }

.mv__main {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}

.mv__number {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-weight: 600;
  color: var(--text-primary);
}

.mv__meta {
  color: var(--text-muted);
  font-size: var(--text-xs);
  overflow-wrap: anywhere;
}

.mv__badge {
  padding: 0.05rem 0.4rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: var(--text-xs);
  font-weight: 500;
}
.mv__badge--installed {
  border-color: var(--primary);
  color: var(--primary);
}
.mv__badge--warn {
  border-color: var(--warning);
  color: var(--warning);
}

.mv__toggle {
  margin-top: var(--space-3);
  padding: 0;
  border: 0;
  background: none;
  color: var(--primary);
  font-size: var(--text-xs);
  cursor: pointer;
}
.mv__toggle:hover { text-decoration: underline; }

.mv__warn {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--warning) 10%, transparent);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}
</style>
