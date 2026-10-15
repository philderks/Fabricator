<script setup>
import { computed } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import SearchResultCard from '../../components/ui/SearchResultCard.vue'
import { formatFileSize } from '../../utils/format'
import { installedModDisplayName } from '../../utils/installedModDisplay'
import { modrinthProjectUrl } from '../../utils/modrinthUrl'
import { useServerStore } from '../../stores/server'
import { isPluginLoader } from '../../utils/loaderKind'
import { t } from '../../i18n'

const store = useServerStore()

const onSearch = (event) => { store.modSearch = event.target.value }

/** Version + size, matching the browse modal's meta line. Version is the
 *  Modrinth release when the install manifest knows it, else 'local'. */
const modMeta = (mod) => {
  const parts = []
  if (mod.disabled) parts.push(t('mods.meta.disabled'))
  if (mod.version) parts.push(mod.version)
  const update = store.modUpdates[mod.filename]
  if (update) parts.push(t('mods.meta.update', { version: update.versionNumber }))
  if (mod.size) parts.push(formatFileSize(mod.size))
  return parts.join(' · ')
}

const updateCount = computed(() => Object.keys(store.modUpdates).length)

const showEmpty = computed(() => !store.modsLoading && store.filteredMods.length === 0)

// Add-on vocabulary (Mods vs Plugins) driven by the server's loader. Each
// wording is its own message rather than a noun spliced into one sentence, so
// a translation can inflect the sentence around it.
const isPlugin = computed(() => isPluginLoader(store.server?.loader))
const tk = (modKey, pluginKey, ...args) => t(isPlugin.value ? pluginKey : modKey, ...args)

// The bar is permanent now, so its label has to carry the idle state too —
// previously "select all" only existed as a footer that appeared when nothing
// was selected, and the bar only when something was.
// Early stages (resolving the pack, fetching the archive) and the whole loader
// half report no file count, so the bar runs indeterminate until the per-file
// download begins.
const hasInstallTotal = computed(() => store.backgroundModpack?.determinate === true)

const selectAllLabel = computed(() => {
  if (store.allFilteredSelected) return t('mods.deselectAll')
  if (store.selectedCount > 0) return t('mods.selected', { n: store.selectedCount })
  return tk('mods.selectAllMods', 'mods.selectAllPlugins', store.filteredMods.length)
})
</script>

<template>
  <div class="mods-page">
    <div class="mods-page__header">
      <input
        type="search"
        class="mods-page__search"
        :placeholder="tk('mods.searchMods', 'mods.searchPlugins')"
        :value="store.modSearch"
        @input="onSearch"
      />
      <div class="mods-page__actions">
        <AppButton
          v-if="updateCount > 0"
          variant="ghost"
          :loading="store.updatingMods"
          @click="store.updateAllMods"
        >
          {{ tk('mods.updateMods', 'mods.updatePlugins', updateCount) }}
        </AppButton>
        <AppButton v-if="!isPlugin" variant="ghost" @click="store.openModpackBrowser">{{ $t('mods.browseModpacks') }}</AppButton>
        <AppButton
          variant="primary"
          :loading="store.isInstalling"
          @click="store.openModBrowser"
        >
          {{ tk('mods.browseMods', 'mods.browsePlugins') }}
        </AppButton>
      </div>
    </div>

    <!-- A pack installed from the create modal keeps downloading after the
         modal is gone, so this is the only place that install is visible. -->
    <Panel v-if="store.backgroundModpackInstalling" :title="tk('mods.installingMods', 'mods.installingPlugins')">
      <div class="mods-page__install">
        <div class="mods-page__install-head">
          <span class="mods-page__install-label">{{ store.backgroundModpackLabel }}</span>
          <span v-if="hasInstallTotal" class="mods-page__install-pct">
            {{ store.backgroundModpackPercent }}%
          </span>
        </div>
        <div class="mods-page__install-track">
          <div
            class="mods-page__install-fill"
            :class="{ 'is-indeterminate': !hasInstallTotal }"
            :style="hasInstallTotal ? { width: `${store.backgroundModpackPercent}%` } : null"
          ></div>
        </div>
        <p v-if="store.backgroundModpack?.name" class="mods-page__install-detail">
          {{ store.backgroundModpack.name }}
        </p>
        <p v-if="store.backgroundModpack?.detail" class="mods-page__install-detail">
          {{ store.backgroundModpack.detail }}
        </p>
      </div>
    </Panel>

    <Panel v-if="store.activeModpack" :title="$t('modpacks.active')">
      <div class="mods-page__modpack">
        <span class="mods-page__modpack-name">{{ store.activeModpack.name || store.activeModpack.projectId }}</span>
        <span class="mods-page__modpack-version">{{ store.activeModpack.version }}</span>
        <a
          v-if="modrinthProjectUrl(store.activeModpack)"
          class="mods-page__modrinth-link"
          :href="modrinthProjectUrl(store.activeModpack)"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="$t('modpacks.openOnModrinth')"
        >
          Modrinth
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
            <path d="M4.5 1.5H10.5V7.5" />
            <path d="M10.5 1.5L5 7" />
            <path d="M9 8v2.5H1.5V3H4" />
          </svg>
        </a>
      </div>
    </Panel>

    <Panel :title="tk('mods.installedMods', 'mods.installedPlugins')" :padded="false">
      <!-- Selection toolbar. Present whenever there is a list to act on, so the
           checkbox is somewhere predictable instead of appearing only once a
           selection exists; it picks up the accent treatment when one does. -->
      <div
        v-if="!store.modsLoading && store.filteredMods.length > 0"
        class="mods-page__bulk-bar"
        :class="{ 'is-active': store.selectedCount > 0 }"
      >
        <label class="mods-page__select-all">
          <input
            type="checkbox"
            class="mods-page__checkbox"
            :checked="store.allFilteredSelected"
            :indeterminate.prop="store.selectedCount > 0 && !store.allFilteredSelected"
            @change="store.toggleSelectAllMods"
          />
          <span>{{ selectAllLabel }}</span>
        </label>
        <div v-if="store.selectedCount > 0" class="mods-page__bulk-actions">
          <button
            type="button"
            class="mods-page__bulk-clear"
            @click="store.clearModSelection"
          >
            {{ $t('common.clear') }}
          </button>
          <AppButton
            v-if="store.selectedDisabledCount > 0"
            variant="ghost"
            :loading="store.togglingMods"
            @click="store.setSelectedModsEnabled(true)"
          >
            {{ $t('mods.enableCount', { n: store.selectedDisabledCount }) }}
          </AppButton>
          <AppButton
            v-if="store.selectedEnabledCount > 0"
            variant="ghost"
            :loading="store.togglingMods"
            @click="store.setSelectedModsEnabled(false)"
          >
            {{ $t('mods.disableCount', { n: store.selectedEnabledCount }) }}
          </AppButton>
          <AppButton
            variant="danger"
            :loading="store.bulkDeleting"
            @click="store.handleBulkRemoveMods"
          >
            {{ tk('mods.deleteMods', 'mods.deletePlugins', store.selectedCount) }}
          </AppButton>
        </div>
      </div>

      <div v-if="store.modsLoading" class="mods-page__state">{{ tk('mods.loadingMods', 'mods.loadingPlugins') }}</div>
      <div v-else-if="showEmpty" class="mods-page__state">
        <template v-if="store.modSearch">{{ tk('mods.noMatchMods', 'mods.noMatchPlugins', { query: store.modSearch }) }}</template>
        <template v-else>{{ tk('mods.emptyMods', 'mods.emptyPlugins') }}</template>
      </div>
      <div v-else class="mods-page__grid">
        <SearchResultCard
          v-for="mod in store.filteredMods"
          :key="mod.path"
          :icon-url="mod.iconUrl"
          :title="installedModDisplayName(mod)"
          :description="mod.filename"
          :meta="modMeta(mod)"
          :selected="store.selectedModPaths.has(mod.path)"
          :class="{ 'mods-page__card--disabled': mod.disabled }"
        >
          <template #lead>
            <label
              class="mods-page__item-checkbox-label"
              :aria-label="$t('mods.select', { name: installedModDisplayName(mod) })"
            >
              <input
                type="checkbox"
                class="mods-page__checkbox"
                :checked="store.selectedModPaths.has(mod.path)"
                @change="store.toggleModSelection(mod)"
              />
            </label>
          </template>
          <div class="mods-page__item-actions">
            <a
              v-if="modrinthProjectUrl(mod)"
              class="mods-page__modrinth-link"
              :href="modrinthProjectUrl(mod)"
              target="_blank"
              rel="noopener noreferrer"
              :title="$t('mods.openOnModrinth', { name: installedModDisplayName(mod) })"
              :aria-label="$t('mods.openOnModrinthLabel', { name: installedModDisplayName(mod) })"
            >
              Modrinth
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                <path d="M4.5 1.5H10.5V7.5" />
                <path d="M10.5 1.5L5 7" />
                <path d="M9 8v2.5H1.5V3H4" />
              </svg>
            </a>
            <button
              v-if="modrinthProjectUrl(mod) && !mod.disabled"
              type="button"
              class="mods-page__version-btn"
              :title="$t('mods.changeVersion', { name: installedModDisplayName(mod) })"
              @click="store.openVersionPicker(mod)"
            >
              {{ $t('mods.version') }}
            </button>
            <button type="button" class="mods-page__remove" @click="store.handleRemoveMod(mod)">{{ $t('common.remove') }}</button>
          </div>
        </SearchResultCard>
      </div>

    </Panel>
  </div>
</template>

<style scoped>
.mods-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.mods-page__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.mods-page__search {
  flex: 1;
  height: 32px;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: var(--text-sm);
}

.mods-page__search:focus {
  outline: none;
  border-color: var(--primary);
}

.mods-page__actions {
  display: flex;
  gap: var(--space-2);
}

.mods-page__install {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mods-page__install-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.mods-page__install-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.mods-page__install-pct {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.mods-page__install-track {
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-tertiary);
  overflow: hidden;
}

.mods-page__install-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--primary);
  transition: width 0.3s ease;
}

/* No file count yet, so show motion rather than a bar stuck at zero. */
.mods-page__install-fill.is-indeterminate {
  width: 35%;
  animation: mods-install-slide 1.1s ease-in-out infinite;
}

@keyframes mods-install-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(340%); }
}

.mods-page__install-detail {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
  overflow-wrap: anywhere;
}

@media (prefers-reduced-motion: reduce) {
  .mods-page__install-fill.is-indeterminate {
    animation: none;
  }
}

.mods-page__modpack {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.mods-page__modpack-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.mods-page__modpack-version {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.mods-page__state {
  padding: var(--space-5) var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

/* ── Bulk action toolbar ───────────────────────────────── */
/* Idle it is just the list's header rule; the accent is what marks an active
   selection, so it can't be baked in now that the bar is always on screen. */
.mods-page__bulk-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  gap: var(--space-3);
  min-height: 44px;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.mods-page__bulk-bar.is-active {
  background: color-mix(in srgb, var(--primary) 8%, var(--bg-secondary));
  border-bottom-color: color-mix(in srgb, var(--primary) 20%, var(--border-color));
}

.mods-page__select-all {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  user-select: none;
}

.mods-page__bulk-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.mods-page__bulk-clear {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  padding: 4px 10px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.mods-page__bulk-clear:hover {
  color: var(--text-secondary);
  border-color: var(--text-muted);
}

/* ── Mod list ──────────────────────────────────────────── */
/* Cards, not rows — same SearchResultCard the browse modal uses, so an
   installed item looks like the search hit it came from. */
.mods-page__grid {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
}

/* Disabled jars (#83): dim the content, not the checkbox or actions, so the
   row can still be selected and re-enabled. */
.mods-page__card--disabled :deep(.search-result-card__icon),
.mods-page__card--disabled :deep(.search-result-card__body) {
  opacity: 0.45;
  filter: grayscale(1);
}

.mods-page__item-checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;
}

.mods-page__checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary);
}

.mods-page__item-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.mods-page__modrinth-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  text-decoration: none;
  padding: 4px 10px;
  white-space: nowrap;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.mods-page__modrinth-link:hover {
  color: var(--primary);
  border-color: var(--primary);
}

.mods-page__modrinth-link:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.mods-page__remove {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  padding: 4px 10px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

/* Same quiet chip as Remove, but non-destructive — it keeps the neutral
   hover colour rather than turning red. */
.mods-page__version-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  padding: 4px 10px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.mods-page__version-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}

.mods-page__remove:hover {
  color: var(--danger);
  border-color: var(--danger);
}

.mods-page__remove:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* ── Select-all footer ─────────────────────────────────── */
/* Mobile: search and the two browse buttons want ~440px between them; below
   that the search takes its own row and the buttons split the next one. */
@media (max-width: 768px) {
  .mods-page__header {
    flex-wrap: wrap;
  }

  .mods-page__search {
    flex: 1 0 100%;
    height: 36px;
  }

  .mods-page__actions {
    flex: 1;
  }

  .mods-page__actions > * {
    flex: 1;
  }

  .mods-page__bulk-bar {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }
}
</style>
