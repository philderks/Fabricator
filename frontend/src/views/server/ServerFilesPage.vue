<script setup>
import ServerFilesTab from '../../components/server/ServerFilesTab.vue'
import { useServerContext } from '../../composables/useServerContext'

const ctx = useServerContext()

const onRefresh = () => ctx.openFileBrowser(ctx.fileBrowser.value.currentPath)
</script>

<template>
  <ServerFilesTab
    :server-id="ctx.serverId.value"
    :file-browser="ctx.fileBrowser.value"
    :format-file-size="ctx.formatFileSize"
    @go-up="ctx.goUpDirectory"
    @refresh="onRefresh"
    @enter-entry="ctx.enterFileEntry"
  />
</template>
