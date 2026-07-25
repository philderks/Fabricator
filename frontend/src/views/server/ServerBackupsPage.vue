<script setup>
import { computed, onMounted, onUnmounted, watch } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import BackupStatsStrip from '../../components/backups/BackupStatsStrip.vue'
import SnapshotsTable from '../../components/backups/SnapshotsTable.vue'
import ManageConfigsPanel from '../../components/backups/ManageConfigsPanel.vue'
import RestoreModeModal from '../../components/modals/RestoreModeModal.vue'
import DeleteBackupConfigModal from '../../components/modals/DeleteBackupConfigModal.vue'
import QuickBackupModal from '../../components/modals/QuickBackupModal.vue'
import ImportWorldModal from '../../components/modals/ImportWorldModal.vue'
import ConfirmModal from '../../components/modals/ConfirmModal.vue'
import { useBackupsStore } from '../../stores/backups'
import { useAuthStore } from '../../stores/auth'
import { useServerStore } from '../../stores/server'

const store = useBackupsStore()
const auth = useAuthStore()
const serverStore = useServerStore()

const TYPE_FILTERS = [
  { value: 'all',     label: 'All'      },
  { value: 'backup',  label: 'Backups'  },
  { value: 'safety',  label: 'Safety'   },
  { value: 'restore', label: 'Restores' },
  { value: 'import',  label: 'Imports'  }
]

const configsById = computed(() => {
  const map = {}
  for (const c of store.configs) map[c.id] = c
  return map
})

const filtered = computed(() => store.filteredSnapshots)

const busySnapshotId = computed(() => {
  if (store.activeJob?.active && store.activeJob?.kind === 'restore') return store.activeJob.snapshotId
  return null
})

const activeJobLabel = computed(() => {
  const job = store.activeJob
  if (!job?.active) return ''
  const phase = job.phase || 'starting'
  const kind = job.kind === 'restore'
    ? 'Restore'
    : job.kind === 'world_import'
      ? 'World import'
      : 'Backup'
  return `${kind} · ${phase.replace(/_/g, ' ')}`
})

function onRestoreRequest(snapshot) {
  store.requestRestoreSnapshot(snapshot)
}

function onSnapshotDeleteRequest(snapshot) {
  store.requestDeleteSnapshot(snapshot)
}

function onConfigDeleteRequest(config) {
  store.requestDeleteConfig(config)
}

const configBeingDeleted = computed(() => store.configToDelete)
const snapshotsForDeleteModal = computed(() => {
  const id = configBeingDeleted.value?.id
  if (!id) return []
  return store.snapshotsByConfigId.get(id) || []
})

watch(
  () => serverStore.currentServerId,
  (id, oldId) => {
    if (!id || id === oldId) return
    if (auth.managed) return
    store.resetState()
    store.loadAll()
  }
)

onMounted(() => {
  if (auth.managed) return
  store.loadAll()
})

onUnmounted(() => {
  store.stopJobPolling()
})
</script>

<template>
  <div v-if="!auth.managed" class="backups-page">
    <!-- Top toolbar -->
    <header class="backups-page__toolbar">
      <div class="backups-page__title-block">
        <h2 class="backups-page__title">Backups</h2>
        <p class="backups-page__sub">
          Snapshots, schedules and restore points for this server.
        </p>
      </div>
      <div class="backups-page__top-actions">
        <AppButton variant="ghost" size="md" @click="store.openCreateConfig()">Schedules</AppButton>
        <AppButton
          variant="ghost"
          size="md"
          :disabled="store.activeJob?.active || store.importUploading"
          @click="store.openImportWorldModal()"
        >
          Import world
        </AppButton>
        <AppButton
          variant="primary"
          size="md"
          :disabled="store.activeJob?.active"
          @click="store.openQuickBackupModal()"
        >
          Quick backup
        </AppButton>
      </div>
    </header>

    <!-- Stats strip -->
    <BackupStatsStrip :summary="store.summary" :loading="store.summaryLoading" />

    <!-- Active job pill -->
    <div v-if="store.activeJob?.active" class="backups-page__job">
      <span class="backups-page__job-dot" aria-hidden="true"></span>
      <span class="backups-page__job-label">{{ activeJobLabel }}</span>
      <span class="backups-page__job-hint">polling…</span>
    </div>

    <!-- Retained files banner (after non-purge delete) -->
    <div v-if="store.retainedFilesBanner" class="backups-page__retained">
      <div class="backups-page__retained-header">
        <strong>Archive files retained on disk</strong>
        <button
          type="button"
          class="backups-page__retained-dismiss"
          @click="store.dismissRetainedFilesBanner()"
        >
          Dismiss
        </button>
      </div>
      <p class="backups-page__retained-text">
        Deleted <code>{{ store.retainedFilesBanner.configName }}</code> kept
        {{ store.retainedFilesBanner.retainedFiles }} archive file{{ store.retainedFilesBanner.retainedFiles === 1 ? '' : 's' }} on disk:
      </p>
      <ul class="backups-page__retained-paths">
        <li v-for="(path, i) in store.retainedFilesBanner.retainedPaths" :key="i">
          <code>{{ path }}</code>
        </li>
      </ul>
    </div>

    <!-- Filters + search -->
    <div class="backups-page__filters">
      <div class="backups-page__type-pills" role="tablist" aria-label="Filter by type">
        <button
          v-for="opt in TYPE_FILTERS"
          :key="opt.value"
          type="button"
          class="backups-page__pill"
          :class="{ 'is-active': store.typeFilter === opt.value }"
          @click="store.typeFilter = opt.value"
        >
          {{ opt.label }}
        </button>
      </div>

      <select
        v-model="store.configFilter"
        class="backups-page__config-select"
        aria-label="Filter by config"
      >
        <option value="all">All configs</option>
        <option value="__manual__">Manual (no config)</option>
        <option v-for="c in store.sortedConfigs" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>

      <div class="backups-page__search">
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <circle cx="6" cy="6" r="4"/>
          <path d="M9 9l3 3"/>
        </svg>
        <input
          v-model="store.search"
          type="search"
          placeholder="Search snapshots…"
          aria-label="Search snapshots"
        />
      </div>
    </div>

    <SnapshotsTable
      :snapshots="filtered"
      :configs-by-id="configsById"
      :server-id="serverStore.currentServerId"
      :busy-snapshot-id="busySnapshotId"
      :loading="store.snapshotsLoading"
      @restore="onRestoreRequest"
      @delete="onSnapshotDeleteRequest"
    />

    <!-- Manage configs slide-in -->
    <ManageConfigsPanel
      :show="store.showManagePanel"
      @close="store.closeManagePanel()"
      @request-delete-config="onConfigDeleteRequest"
    />

    <!-- Restore-mode modal (page-level — page is the long-running view) -->
    <RestoreModeModal
      :show="store.showRestoreModal"
      :snapshot="store.snapshotToRestore"
      :active-job="store.activeJob"
      @confirm="store.confirmRestore"
      @cancel="store.cancelRestore()"
    />

    <!-- Delete-config modal (explicit purge checkbox, unchecked by default) -->
    <DeleteBackupConfigModal
      :show="store.showDeleteConfigModal"
      :config="store.configToDelete"
      :config-snapshots="snapshotsForDeleteModal"
      :loading="store.deletingConfig"
      @confirm="store.confirmDeleteConfig"
      @cancel="store.cancelDeleteConfig()"
    />

    <!-- Quick backup modal (config-free one-off) -->
    <QuickBackupModal
      :show="store.showQuickBackupModal"
      :active-job="store.activeJob"
      :default-storage-path="store.defaultStoragePath"
      @confirm="store.runQuickBackup"
      @cancel="store.closeQuickBackupModal()"
    />

    <!-- Import world modal (upload an archive to replace the active world) -->
    <ImportWorldModal
      :show="store.showImportWorldModal"
      :uploading="store.importUploading"
      :upload-pct="store.importUploadPct"
      :active-job="store.activeJob"
      @confirm="store.importWorld"
      @cancel="store.closeImportWorldModal()"
      @cancel-upload="store.cancelImportUpload()"
    />

    <!-- Snapshot delete confirmation (simple) -->
    <ConfirmModal
      :show="store.showDeleteSnapshotModal"
      title="Delete snapshot"
      :message="store.snapshotToDelete ? `Delete ${store.snapshotToDelete.fileName || store.snapshotToDelete.id}?` : ''"
      description="The archive file and its history record will be removed. This cannot be undone."
      type="danger"
      confirm-text="Delete"
      cancel-text="Cancel"
      :loading="store.deletingSnapshot"
      @confirm="store.confirmDeleteSnapshot()"
      @cancel="store.cancelDeleteSnapshot()"
    />
  </div>
</template>

<style scoped>
.backups-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
}

.backups-page__toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.backups-page__title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.backups-page__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.backups-page__sub {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.backups-page__top-actions {
  display: flex;
  gap: var(--space-2);
}

.backups-page__job {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--primary);
  border-radius: var(--radius-pill);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  width: max-content;
}

.backups-page__job-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  animation: backups-pulse 1.2s ease-in-out infinite;
}

@keyframes backups-pulse {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 1; }
}

.backups-page__job-label {
  text-transform: capitalize;
  color: var(--text-primary);
}

.backups-page__job-hint {
  color: var(--text-muted);
}

.backups-page__retained {
  border: 1px solid var(--warning-dark);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  background: rgba(245, 158, 11, 0.07);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.backups-page__retained-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--warning);
  font-size: var(--text-sm);
}

.backups-page__retained-dismiss {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-xs);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.backups-page__retained-dismiss:hover {
  border-color: var(--text-muted);
  color: var(--text-primary);
}

.backups-page__retained-text {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.backups-page__retained-text code {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.backups-page__retained-paths {
  margin: 0;
  padding: 0 0 0 var(--space-4);
  list-style: disc;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.backups-page__retained-paths code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.backups-page__filters {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.backups-page__type-pills {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
}

.backups-page__pill {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-xs);
  padding: 4px var(--space-3);
  border-radius: var(--radius-pill);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.backups-page__pill:hover {
  color: var(--text-primary);
}

.backups-page__pill.is-active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.backups-page__config-select {
  font-size: var(--text-xs);
  padding: 4px var(--space-2);
  height: 28px;
  max-width: 220px;
}

.backups-page__search {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 200px;
  max-width: 360px;
  padding: 4px var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  color: var(--text-muted);
}

.backups-page__search:focus-within {
  border-color: var(--primary);
}

.backups-page__search input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  padding: 2px 0;
  font-size: var(--text-xs);
  color: var(--text-primary);
}
</style>
