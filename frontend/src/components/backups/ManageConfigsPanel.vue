<script setup>
import { computed } from 'vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import ToggleRow from '../ui/ToggleRow.vue'
import { formatFileSize } from '../../utils/format'
import { useBackupsStore } from '../../stores/backups'
import { t } from '../../i18n'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'request-delete-config'])

const store = useBackupsStore()

const isEditing = computed(() => Boolean(store.editingConfigId))
const heading = computed(() => (isEditing.value ? t('backups.config.editTitle') : t('backups.config.newTitle')))

const sortedConfigs = computed(() => store.sortedConfigs)
const draft = computed(() => store.draft)

// Surface the schedule's time zone so "03:00" is unambiguous — the backend
// fires timeOfDay in this zone, not the server's.
const timeOfDayHint = computed(() => {
  const tz = draft.value?.schedule?.timezone
  return tz ? t('backups.config.timeOfDayHintTz', { tz }) : t('backups.config.timeOfDayHint')
})

function statsForConfig(configId) {
  const snaps = store.snapshotsByConfigId.get(configId) || []
  const count = snaps.length
  const bytes = snaps.reduce((acc, snap) => acc + (typeof snap.sizeBytes === 'number' ? snap.sizeBytes : 0), 0)
  return { count, bytes }
}

function selectConfig(config) {
  store.openEditConfig(config)
}

function startCreate() {
  store.openCreateConfig()
}

function onSave() {
  store.saveConfigDraft()
}

function onDelete() {
  const config = store.configById(store.editingConfigId)
  if (config) emit('request-delete-config', config)
}

function onClose() {
  emit('close')
}
</script>

<template>
  <Transition name="manage-panel">
    <div v-if="props.show" class="manage-panel__overlay" @click.self="onClose">
      <aside class="manage-panel" role="dialog" :aria-label="$t('backups.config.panelLabel')">
        <header class="manage-panel__header">
          <h2 class="manage-panel__title">{{ $t('backups.config.panelTitle') }}</h2>
          <button
            type="button"
            class="manage-panel__close"
            :disabled="store.savingConfig"
            :aria-label="$t('common.close')"
            @click="onClose"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </header>

        <div class="manage-panel__body">
          <aside class="manage-panel__list" :aria-label="$t('backups.config.listLabel')">
            <button
              type="button"
              class="manage-panel__list-create"
              :class="{ 'is-active': !isEditing && props.show }"
              @click="startCreate"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="M6 1v10M1 6h10"/>
              </svg>
              <span>{{ $t('backups.config.newConfig') }}</span>
            </button>
            <ul v-if="sortedConfigs.length" class="manage-panel__list-items">
              <li v-for="config in sortedConfigs" :key="config.id">
                <button
                  type="button"
                  class="manage-panel__list-item"
                  :class="{ 'is-active': store.editingConfigId === config.id }"
                  @click="selectConfig(config)"
                >
                  <div class="manage-panel__list-name">{{ config.name || $t('backups.config.unnamed') }}</div>
                  <div class="manage-panel__list-meta">
                    <span
                      class="manage-panel__list-dot"
                      :class="config.schedule?.enabled ? 'is-on' : 'is-off'"
                      :title="config.schedule?.enabled ? $t('backups.config.scheduled') : $t('backups.config.manualOnly')"
                      aria-hidden="true"
                    ></span>
                    <span>{{ $t('backups.config.snapshotCount', statsForConfig(config.id).count) }}</span>
                    <span>·</span>
                    <span>{{ formatFileSize(statsForConfig(config.id).bytes) }}</span>
                  </div>
                </button>
              </li>
            </ul>
            <p v-else class="manage-panel__list-empty">{{ $t('backups.config.empty') }}</p>
          </aside>

          <section class="manage-panel__editor">
            <header class="manage-panel__editor-header">
              <h3>{{ heading }}</h3>
              <div v-if="isEditing" class="manage-panel__editor-actions">
                <AppButton
                  variant="ghost"
                  size="sm"
                  :disabled="store.activeJob?.active || !!store.runningConfigId || store.savingConfig || store.deletingConfig"
                  @click="store.runBackup(store.editingConfigId)"
                >
                  {{ $t('backups.config.runNow') }}
                </AppButton>
                <AppButton
                  variant="ghost"
                  size="sm"
                  :disabled="store.savingConfig || store.deletingConfig"
                  @click="onDelete"
                >
                  {{ $t('common.delete') }}
                </AppButton>
              </div>
            </header>

            <form class="manage-panel__form" @submit.prevent="onSave">
              <FormField :label="$t('backups.config.name')" :hint="$t('backups.config.nameHint')">
                <template #default="{ id, describedBy }">
                  <input
                    :id="id"
                    v-model="draft.name"
                    type="text"
                    :placeholder="$t('backups.config.namePlaceholder')"
                    :aria-describedby="describedBy"
                  />
                </template>
              </FormField>

              <FormField :label="$t('common.storagePathOptional')" :hint="$t('common.storagePathHint')">
                <template #default="{ id, describedBy }">
                  <input
                    :id="id"
                    v-model="draft.storagePath"
                    type="text"
                    :placeholder="$t('common.storagePathPlaceholder')"
                    :aria-describedby="describedBy"
                  />
                </template>
              </FormField>

              <div class="manage-panel__form-row">
                <FormField :label="$t('backups.config.maxSnapshots')" :hint="$t('backups.config.maxSnapshotsHint')">
                  <template #default="{ id, describedBy }">
                    <input
                      :id="id"
                      v-model.number="draft.maxSnapshots"
                      type="number"
                      min="0"
                      step="1"
                      :aria-describedby="describedBy"
                    />
                  </template>
                </FormField>

                <FormField :label="$t('backups.config.exclusions')" :hint="$t('backups.config.exclusionsHint')">
                  <template #default="{ id, describedBy }">
                    <textarea
                      :id="id"
                      v-model="draft.exclusions"
                      class="manage-panel__textarea"
                      rows="3"
                      placeholder="logs/**\ncrash-reports/**"
                      :aria-describedby="describedBy"
                    ></textarea>
                  </template>
                </FormField>
              </div>

              <div class="manage-panel__toggles">
                <ToggleRow v-model="draft.flush" :label="$t('backups.config.flush')" />
                <ToggleRow v-model="draft.shutdown" :label="$t('backups.config.shutdown')" />
                <ToggleRow v-model="draft.compress" :label="$t('backups.config.compress')" />
              </div>

              <fieldset class="manage-panel__schedule">
                <legend>{{ $t('backups.config.schedule') }}</legend>
                <div class="manage-panel__form-row">
                  <FormField :label="$t('backups.config.frequency')">
                    <template #default="{ id, describedBy }">
                      <select
                        :id="id"
                        v-model.number="draft.schedule.frequencyHours"
                        :aria-describedby="describedBy"
                      >
                        <option v-for="hours in store.frequencyPresets" :key="hours" :value="hours">
                          {{ hours === 1 ? $t('backups.config.everyHour') : hours === 24 ? $t('backups.config.daily') : hours === 168 ? $t('backups.config.weekly') : $t('backups.config.everyHours', { hours }) }}
                        </option>
                      </select>
                    </template>
                  </FormField>

                  <FormField :label="$t('backups.config.timeOfDay')" :hint="timeOfDayHint">
                    <template #default="{ id, describedBy }">
                      <input
                        :id="id"
                        v-model="draft.schedule.timeOfDay"
                        type="time"
                        :aria-describedby="describedBy"
                      />
                    </template>
                  </FormField>
                </div>
              </fieldset>

              <p v-if="store.draftError" class="manage-panel__error">{{ store.draftError }}</p>

              <footer class="manage-panel__form-actions">
                <AppButton
                  variant="ghost"
                  size="md"
                  :disabled="store.savingConfig"
                  @click="onClose"
                >
                  {{ $t('common.close') }}
                </AppButton>
                <AppButton
                  variant="primary"
                  size="md"
                  :loading="store.savingConfig"
                  :disabled="store.savingConfig"
                  type="submit"
                  @click.prevent="onSave"
                >
                  {{ isEditing ? $t('common.saveChanges') : $t('backups.config.create') }}
                </AppButton>
              </footer>
            </form>
          </section>
        </div>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.manage-panel__overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.manage-panel {
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  width: 100%;
  max-width: 920px;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

.manage-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-color);
}

.manage-panel__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
}

.manage-panel__close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease, color 0.15s ease;
}

.manage-panel__close:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.manage-panel__body {
  flex: 1;
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 0;
}

.manage-panel__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
}

.manage-panel__list-create {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  text-align: left;
  background: var(--bg-tertiary);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.manage-panel__list-create.is-active,
.manage-panel__list-create:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.manage-panel__list-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.manage-panel__list-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  text-align: left;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.manage-panel__list-item:hover {
  background: var(--bg-tertiary);
}

.manage-panel__list-item.is-active {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.manage-panel__list-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.manage-panel__list-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.manage-panel__list-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.manage-panel__list-dot.is-on {
  background: var(--success);
}

.manage-panel__list-dot.is-off {
  background: var(--text-disabled);
}

.manage-panel__list-empty {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-disabled);
  padding: var(--space-2) var(--space-3);
}

.manage-panel__editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.manage-panel__editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-color);
}

.manage-panel__editor-header h3 {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.manage-panel__editor-actions {
  display: flex;
  gap: var(--space-2);
}

.manage-panel__form {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-5);
  overflow-y: auto;
}

.manage-panel__form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  min-width: 0;
}

.manage-panel__form-row.is-dimmed {
  opacity: 0.55;
}

.manage-panel__textarea {
  width: 100%;
  min-height: 72px;
  resize: vertical;
  font-family: var(--font-mono);
}

.manage-panel__toggles {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 0 var(--space-4);
  background: var(--bg-primary);
}

.manage-panel__toggles :deep(.toggle-row) {
  border-bottom: 1px solid var(--border-color);
}

.manage-panel__toggles :deep(.toggle-row:last-child) {
  border-bottom: none;
}

.manage-panel__schedule {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4) var(--space-4);
  background: var(--bg-primary);
  margin: 0;
}

.manage-panel__schedule legend {
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.manage-panel__error {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  color: var(--danger);
  font-size: var(--text-sm);
}

.manage-panel__form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  border-top: 1px solid var(--border-color);
  padding-top: var(--space-4);
}

.manage-panel-enter-active,
.manage-panel-leave-active {
  transition: opacity 0.2s ease;
}

.manage-panel-enter-active .manage-panel,
.manage-panel-leave-active .manage-panel {
  transition: transform 0.2s ease;
}

.manage-panel-enter-from,
.manage-panel-leave-to {
  opacity: 0;
}

.manage-panel-enter-from .manage-panel,
.manage-panel-leave-to .manage-panel {
  transform: translateX(40px);
}

@media (max-width: 800px) {
  .manage-panel__body {
    grid-template-columns: 1fr;
  }
  .manage-panel__list {
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    max-height: 200px;
  }
  .manage-panel__form-row {
    grid-template-columns: 1fr;
  }
}
/* Mobile: the panel is already width:100% under a 920px cap, so it fills the
   screen — the border and radius are all that still read as "drawer". */
@media (max-width: 768px) {
  .manage-panel {
    border-left: none;
  }
}
</style>
