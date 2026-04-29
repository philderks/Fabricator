<script setup>
import { onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '../components/layout/AppSidebar.vue'
import AppTopbar from '../components/layout/AppTopbar.vue'
import ConfirmModal from '../components/modals/ConfirmModal.vue'
import JavaInstallModal from '../components/modals/JavaInstallModal.vue'
import ModBrowserModal from '../components/modals/ModBrowserModal.vue'
import ModpackBrowserModal from '../components/modals/ModpackBrowserModal.vue'
import ModSideDecisionModal from '../components/modals/ModSideDecisionModal.vue'
import { useServerStore } from '../stores/server'

const route = useRoute()
const store = useServerStore()

// ---------- Polling (owned by layout per Phase 3 architecture) ----------

let logsIntervalId = null
let serverStatusIntervalId = null
let modpackProgressIntervalId = null

function startLogPolling() {
  if (logsIntervalId || route.name !== 'ServerConsole') return
  logsIntervalId = setInterval(() => store.loadLogs(), 4000)
}

function stopLogPolling() {
  if (logsIntervalId) {
    clearInterval(logsIntervalId)
    logsIntervalId = null
  }
}

function startServerStatusPolling() {
  if (serverStatusIntervalId) return
  serverStatusIntervalId = setInterval(() => store.loadServer({ silent: true }), 2500)
}

function stopServerStatusPolling() {
  if (serverStatusIntervalId) {
    clearInterval(serverStatusIntervalId)
    serverStatusIntervalId = null
  }
}

function startModpackProgressPolling() {
  if (modpackProgressIntervalId) return
  store.fetchModpackProgress()
  modpackProgressIntervalId = setInterval(() => store.fetchModpackProgress(), 1500)
}

function stopModpackProgressPolling() {
  if (modpackProgressIntervalId) {
    clearInterval(modpackProgressIntervalId)
    modpackProgressIntervalId = null
  }
  store.clearModpackProgress()
}

// ---------- Route → store synchronization ----------
// The store deliberately does NOT call useRoute() (setup-store route context
// is fragile under HMR). The layout owns this sync. Both watchers use
// immediate: true so the store has the right values before any action runs.
// These run after the polling declarations so the merged route.name watcher
// can call startLogPolling/stopLogPolling without hitting the TDZ.
watch(() => route.params.id, (id) => { store.currentServerId = id }, { immediate: true })
watch(() => route.name, (name) => {
  store.currentRouteName = name
  if (name === 'ServerConsole') {
    store.loadLogs()
    startLogPolling()
  } else {
    stopLogPolling()
  }
  if (name === 'ServerFiles' && !store.fileBrowser.entries.length && !store.fileBrowser.loading) {
    store.openFileBrowser()
  }
}, { immediate: true })

// ---------- Watches ----------

watch(() => store.currentServerId, async (newId, oldId) => {
  if (!newId || newId === oldId) return
  stopLogPolling()
  stopServerStatusPolling()
  store.resetState()
  await store.refreshAll()
  if (route.name === 'ServerConsole') {
    await store.loadLogs()
    startLogPolling()
  }
  startServerStatusPolling()
})

// Drive modpack-progress polling from the store's installing flag.
watch(() => store.modpackInstalling, (installing) => {
  if (installing) startModpackProgressPolling()
  else stopModpackProgressPolling()
})

// ---------- Lifecycle ----------

onMounted(async () => {
  await store.refreshAll()
  startServerStatusPolling()
  if (route.name === 'ServerConsole') {
    await store.loadLogs()
    startLogPolling()
  }
  if (route.name === 'ServerFiles') {
    store.openFileBrowser()
  }
})

onUnmounted(() => {
  stopLogPolling()
  stopServerStatusPolling()
  stopModpackProgressPolling()
})
</script>

<template>
  <div class="server-layout">
    <AppSidebar />
    <div class="server-layout__main">
      <AppTopbar
        :server-status="store.serverStatus"
        :status-label="store.statusLabel"
        :action-state="store.actionState"
        :start-locked="store.startLocked"
        :start-button-label="store.startButtonLabel"
        @start="store.handleStart"
        @stop="store.handleStop"
        @restart="store.handleRestart"
      />
      <main class="server-layout__content">
        <div v-if="store.serverLoading && !store.server" class="server-layout__loading">Loading server data…</div>
        <div v-else-if="!store.server" class="server-layout__loading">Unable to find this server.</div>
        <router-view v-else />
      </main>
    </div>

    <!-- Modals (hosted at layout level so they survive route changes) -->
    <ModBrowserModal
      :show="store.showModBrowser"
      :mc-version="store.server?.version || store.serverStatus.version"
      :loader="(store.server?.loader || store.serverStatus.loader).toLowerCase()"
      @close="store.showModBrowser = false"
      @install="store.handleInstallMod"
    />

    <ModpackBrowserModal
      :show="store.showModpackBrowser"
      :mc-version="store.server?.version || store.serverStatus.version"
      :loader="(store.server?.loader || store.serverStatus.loader).toLowerCase()"
      @close="store.showModpackBrowser = false"
      @install="store.handleInstallModpack"
    />

    <ConfirmModal
      :show="store.showModpackInstallConfirmModal"
      :title="store.modpackInstalling ? 'Installing Modpack...' : 'Confirm Modpack Replace'"
      :message="store.pendingModpackInstall
        ? (store.modpackInstalling
            ? (store.modpackProgressLabel || 'Preparing...')
            : `Install ${store.pendingModpackInstall.title} on this server?`)
        : ''"
      :description="store.modpackInstalling
        ? ''
        : 'Pack-managed folders (mods, config, defaultconfigs, kubejs, scripts) will be replaced. World data, logs and backups stay intact. Server settings may be overwritten if the pack includes them. If some files are unavailable you will be asked whether to continue.'"
      :type="store.modpackInstalling ? 'info' : 'warning'"
      confirm-text="Install"
      cancel-text="Cancel"
      loading-text="Installing..."
      :loading="store.modpackInstalling"
      @confirm="store.confirmModpackInstall"
      @cancel="store.cancelModpackInstallConfirmation"
      @close="store.cancelModpackInstallConfirmation"
    >
      <template #extra>
        <div v-if="store.modpackInstalling" class="install-progress">
          <div class="install-progress__track">
            <div class="install-progress__fill" :style="{ width: store.modpackProgressPercent + '%' }"></div>
          </div>
          <p v-if="store.modpackProgress?.detail" class="install-progress__detail">{{ store.modpackProgress.detail }}</p>
        </div>
        <label v-else class="confirm-checkbox">
          <input type="checkbox" v-model="store.modpackCreateBackup">
          <span>Create backup before installing</span>
        </label>
      </template>
    </ConfirmModal>

    <ConfirmModal
      :show="store.showMissingModsConfirmModal"
      title="Missing Modpack Files"
      :message="store.missingModsReport.length ? `${store.missingModsReport.length} files could not be downloaded.` : ''"
      :description="store.missingModsDescriptionText"
      type="warning"
      confirm-text="Install Anyway"
      cancel-text="Cancel"
      :loading="store.modpackInstalling"
      @confirm="store.confirmInstallWithMissingMods"
      @cancel="store.cancelMissingModsConfirmation"
      @close="store.cancelMissingModsConfirmation"
    />

    <ModSideDecisionModal
      :show="store.showUncertainModsModal"
      :mods="store.uncertainModsReport"
      :mc-version="store.server?.version || store.serverStatus.version"
      :loader="(store.server?.loader || store.serverStatus.loader).toLowerCase()"
      :loading="store.modpackInstalling"
      @confirm="store.confirmUncertainModsDecision"
      @cancel="store.cancelUncertainModsDecision"
      @close="store.cancelUncertainModsDecision"
    />

    <ConfirmModal
      :show="store.showConfirmModal"
      :title="store.confirmModalData.title"
      :message="store.confirmModalData.message"
      :description="store.confirmModalData.description"
      :type="store.confirmModalData.type"
      :confirm-text="store.confirmModalData.confirmText"
      :cancel-text="store.confirmModalData.cancelText"
      @confirm="store.confirmRemoveMod"
      @cancel="store.cancelRemoveMod"
      @close="store.cancelRemoveMod"
    />

    <ConfirmModal
      :show="store.showBackupRestoreModal"
      title="Restore Backup"
      :message="store.backupToRestore ? `Restore ${store.backupToRestore.name}?` : ''"
      description="Restoring will overwrite the current world and configs. Make sure the server is stopped."
      type="warning"
      confirm-text="Restore"
      cancel-text="Cancel"
      :loading="store.restoringBackup"
      @confirm="store.confirmRestoreBackup"
      @cancel="store.cancelRestoreBackup"
      @close="store.cancelRestoreBackup"
    />

    <ConfirmModal
      :show="store.showBackupDeleteModal"
      title="Delete Backup"
      :message="store.backupToDelete ? `Delete ${store.backupToDelete.name}?` : ''"
      description="This backup will be permanently deleted. This action cannot be undone."
      type="danger"
      confirm-text="Delete"
      cancel-text="Cancel"
      :loading="store.deletingBackup"
      @confirm="store.confirmDeleteBackup"
      @cancel="store.cancelDeleteBackup"
      @close="store.cancelDeleteBackup"
    />

    <ConfirmModal
      :show="store.showDeleteServerModal"
      title="Delete Server"
      message="Delete this server permanently?"
      description="All server files and backups will be deleted. This cannot be undone."
      type="danger"
      confirm-text="Delete"
      cancel-text="Cancel"
      :loading="store.deletingServer"
      @confirm="store.confirmDeleteServer"
      @cancel="store.cancelDeleteServer"
      @close="store.cancelDeleteServer"
    />

    <JavaInstallModal
      :show="store.showJavaModal"
      :mc-version="store.server?.version || ''"
      @close="store.showJavaModal = false"
      @java-installed="store.handleJavaInstalled"
    />
  </div>
</template>

<style scoped>
.server-layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.server-layout__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.server-layout__content {
  flex: 1;
  padding: var(--space-5);
  overflow-y: auto;
}

.server-layout__loading {
  color: var(--text-muted);
  font-size: var(--text-sm);
  padding: var(--space-6) var(--space-5);
  text-align: center;
}

.install-progress {
  margin-top: 4px;
}

.install-progress__track {
  height: 6px;
  border-radius: var(--radius-sm);
  background: var(--border-color);
  overflow: hidden;
}

.install-progress__fill {
  height: 100%;
  border-radius: var(--radius-sm);
  background: var(--primary);
  transition: width 0.3s ease;
}

.install-progress__detail {
  margin: 6px 0 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
