<script setup>
import ServerOverviewTab from '../../components/server/ServerOverviewTab.vue'
import { formatBackupTime } from '../../utils/format'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const onModSearch = (value) => { store.modSearch = value }
</script>

<template>
  <ServerOverviewTab
    :server-status="store.serverStatus"
    :players-display="store.playersDisplay"
    :installed-mods="store.installedMods"
    :active-modpack="store.activeModpack"
    :mod-search="store.modSearch"
    :mods-loading="store.modsLoading"
    :filtered-mods="store.filteredMods"
    :ram-metrics="store.ramMetrics"
    :recent-activity="store.recentActivity"
    :install-loading="store.isInstalling"
    :backup-loading="store.backupLoading"
    :backups="store.backups"
    :format-backup-time="formatBackupTime"
    @update:mod-search="onModSearch"
    @browse-mods="store.openModBrowser"
    @browse-modpacks="store.openModpackBrowser"
    @remove-mod="store.handleRemoveMod"
    @update-mod="store.handleUpdateMod"
    @create-backup="store.createBackupAction"
    @open-console="store.goToConsole"
    @open-files="store.goToFiles"
    @scroll-settings="store.goToSettings"
    @request-restore-backup="store.requestRestoreBackup"
    @request-delete-backup="store.requestDeleteBackup"
  />
</template>
