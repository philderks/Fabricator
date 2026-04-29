<script setup>
import { computed } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import { useServerContext } from '../../composables/useServerContext'

const ctx = useServerContext()

const onSearch = (event) => { ctx.modSearch.value = event.target.value }

const showEmpty = computed(() => !ctx.modsLoading.value && ctx.filteredMods.value.length === 0)
const formatBytes = (bytes) => ctx.formatFileSize(bytes)
</script>

<template>
  <div class="mods-page">
    <div class="mods-page__header">
      <input
        type="search"
        class="mods-page__search"
        placeholder="Search installed mods…"
        :value="ctx.modSearch.value"
        @input="onSearch"
      />
      <div class="mods-page__actions">
        <AppButton variant="ghost" @click="ctx.openModpackBrowser">Browse modpacks</AppButton>
        <AppButton
          variant="primary"
          :loading="ctx.installLoading.value || ctx.modpackInstalling.value"
          @click="ctx.openModBrowser"
        >
          Browse mods
        </AppButton>
      </div>
    </div>

    <Panel v-if="ctx.activeModpack.value" title="Active modpack">
      <div class="mods-page__modpack">
        <span class="mods-page__modpack-name">{{ ctx.activeModpack.value.title || ctx.activeModpack.value.projectId }}</span>
        <span class="mods-page__modpack-version">{{ ctx.activeModpack.value.version }}</span>
      </div>
    </Panel>

    <Panel title="Installed mods" :padded="false">
      <div v-if="ctx.modsLoading.value" class="mods-page__state">Loading mods…</div>
      <div v-else-if="showEmpty" class="mods-page__state">
        <template v-if="ctx.modSearch.value">No mods match "{{ ctx.modSearch.value }}".</template>
        <template v-else>No mods installed yet. Use "Browse mods" to add one.</template>
      </div>
      <ul v-else class="mods-page__list">
        <li v-for="mod in ctx.filteredMods.value" :key="mod.path || mod.name" class="mods-page__item">
          <div class="mods-page__item-info">
            <span class="mods-page__item-name">{{ mod.name }}</span>
            <span class="mods-page__item-meta">
              {{ mod.version }}<template v-if="mod.size"> · {{ formatBytes(mod.size) }}</template>
            </span>
          </div>
          <button
            type="button"
            class="mods-page__remove"
            @click="ctx.handleRemoveMod(mod)"
          >
            Remove
          </button>
        </li>
      </ul>
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

.mods-page__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.mods-page__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-color);
}

.mods-page__item:last-child {
  border-bottom: none;
}

.mods-page__item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.mods-page__item-name {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mods-page__item-meta {
  font-size: var(--text-xs);
  color: var(--text-disabled);
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
</style>
