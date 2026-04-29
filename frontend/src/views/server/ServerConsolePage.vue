<script setup>
import ServerConsoleTab from '../../components/server/ServerConsoleTab.vue'
import { useServerContext } from '../../composables/useServerContext'

const ctx = useServerContext()

const onConsoleCommand = (value) => { ctx.consoleCommand.value = value }
</script>

<template>
  <ServerConsoleTab
    :server-status="ctx.serverStatus.value"
    :status-label="ctx.statusLabel.value"
    :logs="ctx.logs.value"
    :logs-loading="ctx.logsLoading.value"
    :console-command="ctx.consoleCommand.value"
    :can-send-command="ctx.canSendCommand.value"
    :command-sending="ctx.commandSending.value"
    @update:console-command="onConsoleCommand"
    @refresh-logs="ctx.loadLogs"
    @send-command="ctx.sendConsoleCommand"
  />
</template>
