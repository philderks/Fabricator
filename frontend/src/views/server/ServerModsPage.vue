<script setup>
import { computed } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import SearchResultCard from '../../components/ui/SearchResultCard.vue'
import { formatFileSize } from '../../utils/format'
import { installedModDisplayName } from '../../utils/installedModDisplay'
import { useServerStore } from '../../stores/server'
import { contentLabel, isPluginLoader } from '../../utils/loaderKind'

const store = useServerStore()

const onSearch = (event) => { store.modSearch = event.target.value }

/** Version + size, matching the browse modal's meta line. Version is the
 *  Modrinth release when the install manifest knows it, else 'local'. */
const modMeta = (mod) => {
  const parts = []
  if (mod.version) parts.push(mod.version)
  if (mod.size) parts.push(formatFileSize(mod.size))
  return parts.join(' · ')
}

const showEmpty = computed(() => !store.modsLoading && store.filteredMods.length === 0)

// Add-on vocabulary (Mods vs Plugins) driven by the server's loader.
const isPlugin = computed(() => isPluginLoader(store.server?.loader))
const noun = computed(() => contentLabel(store.server?.loader, true))
const nounSingular = computed(() => contentLabel(store.server?.loader, false))
const nounLower = computed(() => noun.value.toLowerCase())
</script>

<template>
  <div class="mods-page">
    <div class="mods-page__header">
      <input
        type="search"
        class="mods-page__search"
        :placeholder="`Search installed ${nounLower}…`"
        :value="store.modSearch"
        @input="onSearch"
      />
      <div class="mods-page__actions">
        <AppButton v-if="!isPlugin" variant="ghost" @click="store.openModpackBrowser">Browse modpacks</AppButton>
        <AppButton
          variant="primary"
          :loading="store.isInstalling"
          @click="store.openModBrowser"
        >
          Browse {{ nounLower }}
        </AppButton>
      </div>
    </div>

    <Panel v-if="store.activeModpack" title="Active modpack">
      <div class="mods-page__modpack">
        <span class="mods-page__modpack-name">{{ store.activeModpack.name || store.activeModpack.projectId }}</span>
        <span class="mods-page__modpack-version">{{ store.activeModpack.version }}</span>
      </div>
    </Panel>

    <Panel :title="`Installed ${noun}`" :padded="false">
      <!-- Bulk action toolbar (only visible when at least one mod is selected) -->
      <div v-if="store.selectedCount > 0" class="mods-page__bulk-bar">
        <label class="mods-page__select-all">
          <input
            type="checkbox"
            class="mods-page__checkbox"
            :checked="store.allFilteredSelected"
            :indeterminate.prop="store.selectedCount > 0 && !store.allFilteredSelected"
            @change="store.toggleSelectAllMods"
          />
          <span>{{ store.allFilteredSelected ? 'Deselect all' : `${store.selectedCount} selected` }}</span>
        </label>
        <div class="mods-page__bulk-actions">
          <button
            type="button"
            class="mods-page__bulk-clear"
            @click="store.clearModSelection"
          >
            Clear
          </button>
          <AppButton
            variant="danger"
            :loading="store.bulkDeleting"
            @click="store.handleBulkRemoveMods"
          >
            Delete {{ store.selectedCount }} {{ store.selectedCount === 1 ? nounSingular.toLowerCase() : nounLower }}
          </AppButton>
        </div>
      </div>

      <div v-if="store.modsLoading" class="mods-page__state">Loading {{ nounLower }}…</div>
      <div v-else-if="showEmpty" class="mods-page__state">
        <template v-if="store.modSearch">No {{ nounLower }} match "{{ store.modSearch }}".</template>
        <template v-else>No {{ nounLower }} installed yet. Use "Browse {{ nounLower }}" to add one.</template>
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
        >
          <template #lead>
            <label
              class="mods-page__item-checkbox-label"
              :aria-label="`Select ${installedModDisplayName(mod)}`"
            >
              <input
                type="checkbox"
                class="mods-page__checkbox"
                :checked="store.selectedModPaths.has(mod.path)"
                @change="store.toggleModSelection(mod)"
              />
            </label>
          </template>
          <button type="button" class="mods-page__remove" @click="store.handleRemoveMod(mod)">Remove</button>
        </SearchResultCard>
      </div>

      <!-- Select-all footer (when no items selected, and list is non-empty) -->
      <div
        v-if="!store.modsLoading && store.filteredMods.length > 1 && store.selectedCount === 0"
        class="mods-page__select-all-footer"
      >
        <button type="button" class="mods-page__select-all-btn" @click="store.toggleSelectAllMods">
          Select all {{ store.filteredMods.length }} {{ nounLower }}
        </button>
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

.mods-page__modpack {
  display: flex;
  align-items: baseline;
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
.mods-page__bulk-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  background: color-mix(in srgb, var(--primary) 8%, var(--bg-secondary));
  border-bottom: 1px solid color-mix(in srgb, var(--primary) 20%, var(--border-color));
  gap: var(--space-3);
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

.mods-page__remove:hover {
  color: var(--danger);
  border-color: var(--danger);
}

.mods-page__remove:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* ── Select-all footer ─────────────────────────────────── */
.mods-page__select-all-footer {
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--border-color);
  text-align: center;
}

.mods-page__select-all-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 2px 4px;
  transition: color 0.15s ease;
}

.mods-page__select-all-btn:hover {
  color: var(--primary);
}
</style>
