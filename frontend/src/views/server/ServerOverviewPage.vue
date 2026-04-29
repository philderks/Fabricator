<script setup>
import ServerOverviewTab from '../../components/server/ServerOverviewTab.vue'
import { useServerContext } from '../../composables/useServerContext'

const ctx = useServerContext()

const onModSearch = (value) => { ctx.modSearch.value = value }
</script>

<template>
  <ServerOverviewTab
    :server-status="ctx.serverStatus.value"
    :players-display="ctx.playersDisplay.value"
    :installed-mods="ctx.installedMods.value"
    :active-modpack="ctx.activeModpack.value"
    :mod-search="ctx.modSearch.value"
    :mods-loading="ctx.modsLoading.value"
    :filtered-mods="ctx.filteredMods.value"
    :ram-metrics="ctx.ramMetrics.value"
    :recent-activity="ctx.recentActivity.value"
    :install-loading="ctx.isInstalling.value"
    :backup-loading="ctx.backupLoading.value"
    :backups="ctx.backups.value"
    :format-backup-time="ctx.formatBackupTime"
    @update:mod-search="onModSearch"
    @browse-mods="ctx.openModBrowser"
    @browse-modpacks="ctx.openModpackBrowser"
    @remove-mod="ctx.handleRemoveMod"
    @update-mod="ctx.handleUpdateMod"
    @create-backup="ctx.createBackupAction"
    @open-console="ctx.goToConsole"
    @open-files="ctx.goToFiles"
    @scroll-settings="ctx.goToSettings"
    @request-restore-backup="ctx.requestRestoreBackup"
    @request-delete-backup="ctx.requestDeleteBackup"
  />
</template>
