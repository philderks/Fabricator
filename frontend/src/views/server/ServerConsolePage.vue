<script setup>
import ServerConsoleTab from '../../components/server/ServerConsoleTab.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

const onConsoleCommand = (value) => { store.consoleCommand = value }
</script>

<template>
  <ServerConsoleTab
    :server-status="store.serverStatus"
    :status-label="store.statusLabel"
    :logs="store.logs"
    :logs-loading="store.logsLoading"
    :console-command="store.consoleCommand"
    :can-send-command="store.canSendCommand"
    :command-sending="store.commandSending"
    @update:console-command="onConsoleCommand"
    @refresh-logs="store.loadLogs"
    @send-command="store.sendConsoleCommand"
  />
</template>
