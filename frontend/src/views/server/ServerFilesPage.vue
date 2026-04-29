<script setup>
import ServerFilesTab from '../../components/server/ServerFilesTab.vue'
import { formatFileSize } from '../../utils/format'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const onRefresh = () => store.openFileBrowser(store.fileBrowser.currentPath)
</script>

<template>
  <ServerFilesTab
    :server-id="store.currentServerId"
    :file-browser="store.fileBrowser"
    :format-file-size="formatFileSize"
    @go-up="store.goUpDirectory"
    @refresh="onRefresh"
    @enter-entry="store.enterFileEntry"
  />
</template>
