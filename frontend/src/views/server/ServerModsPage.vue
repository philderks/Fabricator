<script setup>
import { computed } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import { formatFileSize } from '../../utils/format'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const initialOf = (name) => {
  if (!name) return '?'
  return name.replace(/[^a-zA-Z0-9]/g, '').slice(0, 1).toUpperCase() || '?'
}

const onSearch = (event) => { store.modSearch = event.target.value }

const showEmpty = computed(() => !store.modsLoading && store.filteredMods.length === 0)
</script>

<template>
  <div class="mods-page">
    <div class="mods-page__header">
      <input
        type="search"
        class="mods-page__search"
        placeholder="Search installed mods…"
        :value="store.modSearch"
        @input="onSearch"
      />
      <div class="mods-page__actions">
        <AppButton variant="ghost" @click="store.openModpackBrowser">Browse modpacks</AppButton>
        <AppButton
          variant="primary"
          :loading="store.isInstalling"
          @click="store.openModBrowser"
        >
          Browse mods
        </AppButton>
      </div>
    </div>

    <Panel v-if="store.activeModpack" title="Active modpack">
      <div class="mods-page__modpack">
        <span class="mods-page__modpack-name">{{ store.activeModpack.name || store.activeModpack.projectId }}</span>
        <span class="mods-page__modpack-version">{{ store.activeModpack.version }}</span>
      </div>
    </Panel>

    <Panel title="Installed mods" :padded="false">
      <div v-if="store.modsLoading" class="mods-page__state">Loading mods…</div>
      <div v-else-if="showEmpty" class="mods-page__state">
        <template v-if="store.modSearch">No mods match "{{ store.modSearch }}".</template>
        <template v-else>No mods installed yet. Use "Browse mods" to add one.</template>
      </div>
      <ul v-else class="mods-page__list">
        <li v-for="mod in store.filteredMods" :key="mod.path" class="mods-page__item">
          <div class="mods-page__icon" aria-hidden="true">{{ initialOf(mod.name) }}</div>
          <div class="mods-page__item-info">
            <div class="mods-page__item-name-row">
              <span class="mods-page__item-name">{{ mod.name }}</span>
              <span class="mods-page__item-version">{{ mod.version }}</span>
            </div>
            <span class="mods-page__item-meta">
              <template v-if="mod.size">{{ formatFileSize(mod.size) }}</template>
              <template v-else>—</template>
            </span>
          </div>
          <button type="button" class="mods-page__remove" @click="store.handleRemoveMod(mod)">Remove</button>
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
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-color);
}

.mods-page__item:last-child {
  border-bottom: none;
}

.mods-page__item-info {
  flex: 1;
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

.mods-page__icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary);
}

.mods-page__item-name-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-width: 0;
}

.mods-page__item-version {
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
  flex-shrink: 0;
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
</style>
