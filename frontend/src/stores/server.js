import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import {
  installMod,
  installModpack,
  installUploadedModpack,
  getModpackInstallProgress
} from '../api/modrinth'
import {
  getServer,
  getServers,
  getInstalledMods,
  removeMod,
  bulkRemoveMods,
  getServerLogs,
  startServer,
  stopServer,
  restartServer,
  installServer,
  getServerInstallProgress,
  updateServerSettings,
  setServerAutoStart,
  sendServerCommand,
  browseServerFiles,
  searchServerFiles,
  deleteServer,
  getServerFile,
  saveServerFile
} from '../api/servers'
import { useToast } from '../composables/useToast'
import {
  enrichInstalledModsWithModrinth,
  invalidateModrinthMetaCache
} from '../utils/enrichInstalledModsModrinth'
// Status-display logic consolidated in utils/getEffectiveStatus (F6/CC5);
// keep alias for the existing call sites in this file.
import { getEffectiveStatus as pickEffectiveStatus } from '../utils/getEffectiveStatus'

const MODPACK_STAGE_LABELS = {
  starting: 'Starting install...',
  resolving: 'Resolving modpack version...',
  cleaning: 'Cleaning old modpack files...',
  downloading_pack: 'Downloading modpack archive...',
  checking_availability: 'Checking file availability...',
  installing_files: 'Downloading mods...',
  extracting_overrides: 'Extracting override files...',
  done: 'Finishing up...'
}

const TEXT_FILE_EXTENSIONS = new Set([
  'txt', 'json', 'properties', 'yml', 'yaml', 'toml', 'cfg', 'conf', 'log', 'md'
])

// Cap on remembered console commands. Old entries fall off the front so a
// long-lived session can't grow the history without bound.
const MAX_COMMAND_HISTORY = 100

function isTextFile(path) {
  if (!path || typeof path !== 'string') return false
  const segments = path.toLowerCase().split('.')
  const extension = segments.pop() || ''
  return TEXT_FILE_EXTENSIONS.has(extension)
}

export const useServerStore = defineStore('server', () => {
  const router = useRouter()
  const toast = useToast()

  // ---------- State ----------
  // Pushed by ServerLayout via watchers with immediate: true. We do NOT call
  // useRoute() here — setup-store route context is fragile under HMR and
  // call-ordering changes. Layout owns route-to-store synchronization.
  const currentServerId = ref(null)
  const currentRouteName = ref(null)
  const serversList = ref([])

  const server = ref(null)
  const serverLoading = ref(true)
  const modsLoading = ref(false)
  const logsLoading = ref(false)
  const installedMods = ref([])
  const modSearch = ref('')
  const logs = ref({ stdout: [], stderr: [], running: false })
  const serverSettings = ref(null)
  const showModBrowser = ref(false)
  const showJavaModal = ref(false)
  const pendingJavaAction = ref(null)
  const showModpackBrowser = ref(false)
  const showConfirmModal = ref(false)
  const confirmModalData = ref({})
  const modToRemove = ref(null)
  const selectedModPaths = ref(new Set())
  const bulkDeleting = ref(false)
  const installLoading = ref(false)
  const modpackInstalling = ref(false)
  const actionState = ref({ start: false, stop: false, restart: false, install: false })
  const consoleCommand = ref('')
  const commandSending = ref(false)
  // Sent console commands, oldest first — backs the arrow-key recall in
  // ServerConsolePage. Lives in the store (not the component) so history
  // survives navigating away from the console tab and back.
  const commandHistory = ref([])
  // Which history entry is currently being previewed. null means "not
  // recalling" — the input holds the user's own in-progress line.
  const historyIndex = ref(null)
  // The in-progress line stashed when recall begins, so arrowing back down
  // past the newest entry returns what was typed instead of dropping it.
  const historyDraft = ref('')
  const fileBrowser = ref({ currentPath: '', entries: [], loading: false, error: null })
  const fileEditor = ref({ path: null, content: '', originalContent: '', loading: false, saving: false, error: null })
  const fileSearch = ref({ query: '', results: [], active: false, loading: false, truncated: false, error: null })
  const showDeleteServerModal = ref(false)
  const deletingServer = ref(false)
  const modpackProgress = ref(null)
  const showModpackInstallConfirmModal = ref(false)
  const pendingModpackInstall = ref(null)
  const modpackCreateBackup = ref(true)
  const showMissingModsConfirmModal = ref(false)
  const pendingMissingModsInstall = ref(null)
  const missingModsReport = ref([])
  const showUncertainModsModal = ref(false)
  const uncertainModsReport = ref([])
  const pendingUncertainModpackData = ref(null)

  // ---------- Private helpers (not returned) ----------
  const defaultSettings = (data = {}) => ({
    name: data.name || 'Minecraft Server',
    port: data.port ?? 25565,
    serverIp: data.serverIp || '',
    motd: data.motd || 'A Minecraft Server',
    bugReportLink: data.bugReportLink || '',
    maxPlayers: data.maxPlayers ?? 20,
    difficulty: data.difficulty || 'normal',
    gamemode: data.gamemode || 'survival',
    forceGamemode: data.forceGamemode ?? false,
    hardcore: data.hardcore ?? false,
    allowFlight: data.allowFlight ?? false,
    pvp: data.pvp ?? true,
    spawnProtection: data.spawnProtection ?? 16,
    commandBlocks: data.commandBlocks ?? true,
    whitelist: data.whitelist ?? false,
    enforceWhitelist: data.enforceWhitelist ?? false,
    functionPermissionLevel: data.functionPermissionLevel ?? 2,
    opPermissionLevel: data.opPermissionLevel ?? 4,
    playerIdleTimeout: data.playerIdleTimeout ?? 0,
    pauseWhenEmptySeconds: data.pauseWhenEmptySeconds ?? 60,
    onlineMode: data.onlineMode ?? true,
    enforceSecureProfile: data.enforceSecureProfile ?? true,
    hideOnlinePlayers: data.hideOnlinePlayers ?? false,
    preventProxyConnections: data.preventProxyConnections ?? false,
    logIps: data.logIps ?? true,
    acceptsTransfers: data.acceptsTransfers ?? false,
    enableStatus: data.enableStatus ?? true,
    statusHeartbeatInterval: data.statusHeartbeatInterval ?? 0,
    broadcastConsoleToOps: data.broadcastConsoleToOps ?? true,
    broadcastRconToOps: data.broadcastRconToOps ?? true,
    enableCodeOfConduct: data.enableCodeOfConduct ?? false,
    enableJmxMonitoring: data.enableJmxMonitoring ?? false,
    enableQuery: data.enableQuery ?? false,
    queryPort: data.queryPort ?? data.port ?? 25565,
    enableRcon: data.enableRcon ?? false,
    rconPort: data.rconPort ?? 25575,
    rconPassword: data.rconPassword || '',
    rateLimit: data.rateLimit ?? 0,
    networkCompressionThreshold: data.networkCompressionThreshold ?? 256,
    resourcePack: data.resourcePack || '',
    resourcePackPrompt: data.resourcePackPrompt || '',
    resourcePackSha1: data.resourcePackSha1 || '',
    resourcePackId: data.resourcePackId || '',
    requireResourcePack: data.requireResourcePack ?? false,
    initialEnabledPacks: data.initialEnabledPacks || 'vanilla',
    initialDisabledPacks: data.initialDisabledPacks || '',
    textFilteringConfig: data.textFilteringConfig || '',
    textFilteringVersion: data.textFilteringVersion ?? 0,
    viewDistance: data.viewDistance ?? 10,
    simulationDistance: data.simulationDistance ?? 10,
    memory: data.memory ?? 4,
    memoryUnit: data.memoryUnit === 'MB' ? 'MB' : 'GB',
    // Launch tuning (#54). Empty string means "no override": javaPath falls
    // back to the managed JDK matching the MC version, jvmArgs adds nothing.
    javaPath: data.javaPath || '',
    jvmArgs: data.jvmArgs || '',
    levelName: data.levelName || 'world',
    levelType: data.levelType || 'default',
    seed: data.seed || '',
    generatorSettings: data.generatorSettings ?? '',
    maxWorldSize: data.maxWorldSize ?? 29999984,
    generateStructures: data.generateStructures ?? true,
    spawnAnimals: data.spawnAnimals ?? true,
    spawnMonsters: data.spawnMonsters ?? true,
    spawnNpcs: data.spawnNpcs ?? true,
    entityBroadcastRangePercentage: data.entityBroadcastRangePercentage ?? 100,
    maxChainedNeighborUpdates: data.maxChainedNeighborUpdates ?? 1000000,
    maxTickTime: data.maxTickTime ?? 60000,
    syncChunkWrites: data.syncChunkWrites ?? true,
    useNativeTransport: data.useNativeTransport ?? true,
    regionFileCompression: data.regionFileCompression || 'deflate'
  })

  const formatMissingModsDescription = (missingFiles = []) => {
    if (!Array.isArray(missingFiles) || !missingFiles.length) return ''
    const preview = missingFiles.slice(0, 8).map((i) => `- ${i.path}: ${i.reason}`).join('\n')
    // Count items, not preview-string lines — a `reason` containing `\n` would otherwise
    // inflate the line count and underreport `remaining`.
    const remaining = Math.max(0, missingFiles.length - 8)
    const suffix = remaining > 0 ? `\n...and ${remaining} more.` : ''
    return `The following files could not be downloaded:\n${preview}${suffix}\n\nInstall anyway without these files?`
  }

  // ---------- Computeds (getters) ----------
  const modpackProgressLabel = computed(() => {
    const p = modpackProgress.value
    if (!p?.active) return ''
    const stage = MODPACK_STAGE_LABELS[p.stage] || p.stage || 'Working...'
    if (p.stage === 'installing_files' && p.total > 0) {
      return `${stage} (${p.current}/${p.total})`
    }
    return stage
  })

  const modpackProgressPercent = computed(() => {
    const p = modpackProgress.value
    if (!p?.active || !p.total) return 0
    return Math.round((p.current / p.total) * 100)
  })

  const serverStatus = computed(() => {
    const loaderName = server.value?.loader
      ? server.value.loader.charAt(0).toUpperCase() + server.value.loader.slice(1)
      : 'Unknown'

    return {
      name: server.value?.name || 'Minecraft Server',
      // Mirror backend _augment_with_runtime semantics: the runtime registry
      // only knows running/stopped. For in-flight states the persisted
      // status (installing, starting, stopping, failed, pending) is
      // authoritative — picking runtime would display "stopped" while an
      // install thread is actively running.
      status: pickEffectiveStatus(server.value),
      uptime: server.value?.runtime?.uptime || '—',
      version: server.value?.version || '—',
      loader: loaderName,
      players: {
        online: server.value?.runtime?.players?.online ?? 0,
        max: server.value?.maxPlayers ?? server.value?.runtime?.players?.max ?? 0
      },
      tps: server.value?.runtime?.tps ?? null
    }
  })

  const canEditSettings = computed(() => serverStatus.value.status !== 'running')

  const ramMetrics = computed(() => {
    const runtimeRam = server.value?.runtime?.ram
    const runtimeLimit = typeof runtimeRam?.limitGB === 'number' ? runtimeRam.limitGB : null
    // Fallback total (used while stopped, before a real -Xmx limit is known).
    // memory is expressed in memoryUnit; normalize MB to GB so the bar's units
    // stay consistent with used (always GB).
    const configuredUnit = server.value?.memoryUnit ?? serverSettings.value?.memoryUnit ?? 'GB'
    const configuredValue = Number(server.value?.memory ?? serverSettings.value?.memory ?? 0)
    const configuredTotal = configuredUnit === 'MB' ? configuredValue / 1024 : configuredValue
    let total = runtimeLimit ?? configuredTotal
    if (!Number.isFinite(total) || total <= 0) total = 1
    let used = 0
    if (runtimeRam) {
      if (typeof runtimeRam.usedGB === 'number') used = runtimeRam.usedGB
      else if (typeof runtimeRam.usedBytes === 'number') used = runtimeRam.usedBytes / (1024 ** 3)
      else if (typeof runtimeRam.used === 'number') used = runtimeRam.used
    }
    used = Math.max(0, Math.min(used, total))
    return { used, total, running: serverStatus.value.status === 'running' }
  })

  const filteredMods = computed(() => {
    if (!modSearch.value) return installedMods.value
    const q = modSearch.value.toLowerCase()
    return installedMods.value.filter((m) => {
      if (m.name.toLowerCase().includes(q)) return true
      const title = m.displayTitle ? String(m.displayTitle).toLowerCase() : ''
      return title.includes(q)
    })
  })

  const selectedCount = computed(() => selectedModPaths.value.size)

  const allFilteredSelected = computed(() =>
    filteredMods.value.length > 0 &&
    filteredMods.value.every((m) => selectedModPaths.value.has(m.path))
  )

  const playersDisplay = computed(() => {
    const o = serverStatus.value.players.online
    const m = serverStatus.value.players.max
    return m ? `${o}/${m}` : `${o}`
  })

  const statusLabel = computed(() => {
    const s = serverStatus.value.status
    if (s === 'running') return 'Running'
    if (s === 'stopped') return 'Stopped'
    if (s === 'pending') return 'Install Required'
    if (s === 'installing') return 'Installing'
    if (s === 'failed') return 'Failed'
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Unknown'
  })

  const startLocked = computed(() => serverStatus.value.status === 'installing')

  const startButtonLabel = computed(() => {
    if (serverStatus.value.status === 'installing') return 'Installing…'
    if (serverStatus.value.status === 'pending') {
      return actionState.value.install ? 'Installing…' : 'Install'
    }
    return actionState.value.start ? 'Starting…' : 'Start'
  })

  const activeModpack = computed(() => server.value?.modpack || null)

  const isInstalling = computed(() => installLoading.value || modpackInstalling.value)

  const canSendCommand = computed(() => serverStatus.value.status === 'running' && !!server.value)

  // Description for the missing-mods confirm modal. Computed (not a function)
  // so the template binding stays reactive when missingModsReport changes.
  const missingModsDescriptionText = computed(() => formatMissingModsDescription(missingModsReport.value))

  const hasFileChanges = computed(() => {
    if (!fileEditor.value.path) return false
    return fileEditor.value.content !== fileEditor.value.originalContent
  })

  const isDirtySettings = computed(() => {
    if (!server.value || !serverSettings.value) return false
    const baseline = defaultSettings(server.value)
    for (const key of Object.keys(baseline)) {
      if (baseline[key] !== serverSettings.value[key]) return true
    }
    return false
  })

  // ---------- Actions ----------

  async function loadServers() {
    try {
      const list = await getServers()
      if (Array.isArray(list)) {
        serversList.value = list
      }
      return { ok: true }
    } catch (error) {
      // Failure-safe: keep last-known-good state. Switcher pseudo-entry handles empty list.
      // Returns a tuple so opt-in callers (e.g. Servers.vue) can surface the
      // error UI; internal callers ignore the return value.
      return { ok: false, error }
    }
  }

  async function loadServer(options = {}) {
    const { silent = false } = options
    if (!silent) serverLoading.value = true
    try {
      const data = await getServer(currentServerId.value)
      server.value = data
      // Mirror the freshly augmented record into serversList so the sidebar
      // dropdown trigger reflects the same status as the detail page header.
      // ServerLayout polls loadServer every 2.5s; serversList alone is only
      // refreshed on dropdown-open / mount / delete / save — without this
      // patch the trigger badge stays "stopped" while the header says
      // "running" until the user re-opens the dropdown or reloads the page.
      const listIdx = serversList.value.findIndex((s) => s?.id === data?.id)
      if (listIdx >= 0) {
        const next = [...serversList.value]
        next[listIdx] = data
        serversList.value = next
      }
      const mappedSettings = defaultSettings(data)
      if (!serverSettings.value || currentRouteName.value !== 'ServerSettings') {
        serverSettings.value = mappedSettings
      }
    } catch (error) {
      console.error('Failed to load server:', error)
      toast.error('Could not load server details', 'Error')
    } finally {
      if (!silent) serverLoading.value = false
    }
  }

  async function loadMods() {
    modsLoading.value = true
    try {
      const files = await getInstalledMods(currentServerId.value)
      const base = files.map((file) => {
        // `modrinth` is the install manifest the backend recorded at install
        // time — authoritative project identity, title and icon. Jars dropped
        // in by hand have none and fall through to filename-based enrichment.
        const recorded = file.modrinth || null
        return {
          name: file.name,
          filename: file.name,
          displayTitle: recorded?.title || null,
          iconUrl: recorded?.iconUrl || null,
          modrinth: recorded,
          version: recorded?.versionNumber || file.version || 'local',
          downloads: file.downloads || 'N/A',
          size: file.size,
          updatedAt: file.updatedAt,
          path: file.path,
          source: recorded ? 'Modrinth' : 'Local',
          category: 'Mods Folder'
        }
      })
      installedMods.value = base
      // F11/S9: enrich returns a NEW list (does not mutate in place); await
      // it so the icon/title fields render in a single deterministic patch
      // rather than appearing piecemeal via mutated refs. Manifest-backed
      // entries are already complete and are skipped inside the enricher.
      // `serverId` lets it identify the folder by content hash in one request
      // instead of guessing project slugs per filename (#52).
      installedMods.value = await enrichInstalledModsWithModrinth(base, {
        serverId: currentServerId.value
      })
    } catch (error) {
      console.error('Failed to load mods:', error)
      toast.error('Failed to load installed mods', 'Error')
    } finally {
      modsLoading.value = false
    }
  }

  async function loadLogs(limit = 200) {
    if (!server.value || logsLoading.value) return
    logsLoading.value = true
    try {
      logs.value = await getServerLogs(currentServerId.value, { limit })
    } catch (error) {
      console.error('Failed to load logs:', error)
      toast.error('Failed to load console logs', 'Error')
    } finally {
      logsLoading.value = false
    }
  }

  async function refreshAll() {
    await Promise.all([loadServer(), loadMods()])
  }

  async function openFileBrowser(path = '') {
    fileBrowser.value.loading = true
    fileBrowser.value.error = null
    try {
      const data = await browseServerFiles(currentServerId.value, path ? { path } : {})
      fileBrowser.value = { ...data, entries: data.entries, loading: false, error: null }
    } catch (error) {
      console.error('Failed to browse files:', error)
      fileBrowser.value = { currentPath: path, entries: [], loading: false, error: error.message || 'Unable to load files' }
    }
  }

  function enterFileEntry(entry) {
    if (entry.isDir) openFileBrowser(entry.relativePath)
  }

  // Bumped on every search/clear so a slow response from an abandoned query
  // can't overwrite the results of the one the user is actually waiting on.
  let fileSearchToken = 0

  async function searchFiles(query) {
    const trimmed = (query || '').trim()
    const token = ++fileSearchToken

    if (!trimmed) {
      fileSearch.value = { query: '', results: [], active: false, loading: false, truncated: false, error: null }
      return
    }

    fileSearch.value = { ...fileSearch.value, query: trimmed, active: true, loading: true, error: null }
    try {
      const data = await searchServerFiles(currentServerId.value, { q: trimmed })
      if (token !== fileSearchToken) return
      fileSearch.value = {
        query: trimmed,
        results: data.results || [],
        active: true,
        loading: false,
        truncated: Boolean(data.truncated),
        error: null,
      }
    } catch (error) {
      if (token !== fileSearchToken) return
      console.error('Failed to search files:', error)
      fileSearch.value = {
        query: trimmed,
        results: [],
        active: true,
        loading: false,
        truncated: false,
        error: error.message || 'Search failed',
      }
    }
  }

  function clearFileSearch() {
    fileSearchToken += 1
    fileSearch.value = { query: '', results: [], active: false, loading: false, truncated: false, error: null }
  }

  // Leaves search mode and parks the browser on the hit's folder, so the entry
  // the user picked is visible in its real location afterwards.
  function revealSearchHit(entry) {
    clearFileSearch()
    openFileBrowser(entry.isDir ? entry.relativePath : entry.parentPath || '')
  }

  function goUpDirectory() {
    if (!fileBrowser.value.currentPath) return
    const parts = fileBrowser.value.currentPath.split('/').filter(Boolean)
    parts.pop()
    openFileBrowser(parts.join('/'))
  }

  async function openFile(path) {
    if (!isTextFile(path)) {
      toast.error('Only supported text files can be edited', 'Files')
      return
    }
    fileEditor.value = { path, content: '', originalContent: '', loading: true, saving: false, error: null }
    try {
      const file = await getServerFile(currentServerId.value, path)
      fileEditor.value = { path: file.path, content: file.content, originalContent: file.content, loading: false, saving: false, error: null }
    } catch (error) {
      const message = error?.message || 'Unable to open file'
      fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: message }
      toast.error(message, 'Files')
    }
  }

  async function saveFile() {
    if (!fileEditor.value.path || fileEditor.value.saving) return
    fileEditor.value.saving = true
    fileEditor.value.error = null
    try {
      await saveServerFile(currentServerId.value, fileEditor.value.path, fileEditor.value.content)
      fileEditor.value.originalContent = fileEditor.value.content
      toast.success('File saved', 'Files')
    } catch (error) {
      const message = error?.message || 'Failed to save file'
      fileEditor.value.error = message
      toast.error(message, 'Files')
    } finally {
      fileEditor.value.saving = false
    }
  }

  function closeFile() {
    fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: null }
  }

  function openModBrowser() { showModBrowser.value = true }
  function closeModBrowser() { showModBrowser.value = false }
  function openModpackBrowser() { showModpackBrowser.value = true }
  function closeModpackBrowser() { showModpackBrowser.value = false }
  function closeJavaModal() { showJavaModal.value = false }
  function openDeleteServerModal() { showDeleteServerModal.value = true }
  function cancelDeleteServer() { showDeleteServerModal.value = false }
  function setConsoleCommand(value) { consoleCommand.value = value }

  function goToConsole()  { router.push({ name: 'ServerConsole',  params: { id: currentServerId.value } }) }
  function goToFiles()    { router.push({ name: 'ServerFiles',    params: { id: currentServerId.value } }) }
  function goToBackups()  { router.push({ name: 'ServerBackups',  params: { id: currentServerId.value } }) }
  function goToSettings() { router.push({ name: 'ServerSettings', params: { id: currentServerId.value } }) }
  function goToMods()     { router.push({ name: 'ServerMods',     params: { id: currentServerId.value } }) }

  async function confirmDeleteServer() {
    deletingServer.value = true
    try {
      await deleteServer(currentServerId.value)
      toast.success('Server deleted', 'Servers')
      await loadServers()
      router.push({ name: 'Servers' })
    } catch (error) {
      console.error('Failed to delete server:', error)
      toast.error(error.message || 'Failed to delete server', 'Server Error')
    } finally {
      deletingServer.value = false
      showDeleteServerModal.value = false
    }
  }

  async function handleInstallMod(modData) {
    if (!server.value) return
    const prereqs = Array.isArray(modData.prerequisiteMods) ? modData.prerequisiteMods : []
    installLoading.value = true
    try {
      for (const pre of prereqs) {
        if (!pre?.modId) continue
        await installMod(pre.modId, {
          mc_version: modData.mcVersion,
          loader: modData.loader,
          server_id: currentServerId.value
        })
        await loadMods()
      }
      await installMod(modData.modId, {
        mc_version: modData.mcVersion,
        loader: modData.loader,
        server_id: currentServerId.value
      })
      const suffix =
        prereqs.length > 0 ? ` and ${prereqs.length} dependenc${prereqs.length === 1 ? 'y' : 'ies'}` : ''
      toast.success(`${modData.modTitle} installed successfully${suffix}!`, 'Mod Installed')
      await loadMods()
    } catch (error) {
      console.error('Install failed:', error)
      toast.error(error.message || 'Mod installation failed', 'Installation Failed')
      try {
        await loadMods()
      } catch {
        // non-fatal
      }
    } finally {
      installLoading.value = false
    }
  }

  // ── Version picker (#56) ───────────────────────────────────────────────
  // `versionPickerMod` doubles as the open flag and the subject. Null when
  // closed; an installed-mod entry when changing a version; a bare project ref
  // ({ projectId, slug, title }) when picking at install time.
  const versionPickerMod = ref(null)
  const showVersionPicker = computed(() => versionPickerMod.value !== null)

  /**
   * Project identity for the picker, from the manifest when we have it and the
   * filename-derived guess otherwise. Without either there is nothing to list.
   */
  function modProjectRef(mod) {
    const ref_ = mod?.modrinth || mod?.modrinthGuess || null
    if (!ref_?.projectId && !ref_?.slug) return null
    return {
      projectId: ref_.slug || ref_.projectId,
      title: ref_.title || mod?.displayTitle || mod?.name || '',
      // From the manifest when we installed it, otherwise from the hash match
      // (also exact) so a hand-added jar still highlights its current version.
      installedVersionId:
        mod?.modrinth?.versionId || mod?.modrinthGuess?.versionId || '',
      filename: mod?.filename || mod?.name || ''
    }
  }

  function openVersionPicker(mod) {
    const ref_ = modProjectRef(mod)
    if (!ref_) {
      toast.info(
        'This jar could not be matched to a Modrinth project, so its versions are unknown.',
        'No version list'
      )
      return
    }
    versionPickerMod.value = ref_
  }

  function closeVersionPicker() { versionPickerMod.value = null }

  /**
   * Install the chosen version, replacing the jar currently on disk.
   *
   * `replaces` is handled server-side so the old jar is removed only after the
   * new one lands — a failed download leaves the server with the version it
   * already had rather than none at all.
   */
  async function handleSelectVersion({ versionId, versionNumber }) {
    const target = versionPickerMod.value
    if (!target || !server.value) return
    versionPickerMod.value = null
    installLoading.value = true
    try {
      await installMod(target.projectId, {
        mc_version: server.value.version,
        loader: server.value.loader,
        server_id: currentServerId.value,
        version_id: versionId,
        replaces: target.filename || undefined
      })
      // The swapped-out jar's cached title/icon must not stick to the new
      // filename, and the new one needs resolving on the next list.
      if (target.filename) invalidateModrinthMetaCache(target.filename)
      toast.success(
        `${target.title || 'Mod'} is now on version ${versionNumber}`,
        'Version changed'
      )
      await loadMods()
    } catch (error) {
      console.error('Version change failed:', error)
      toast.error(error.message || 'Could not change the mod version', 'Install Failed')
      try {
        await loadMods()
      } catch {
        // non-fatal
      }
    } finally {
      installLoading.value = false
    }
  }

  async function handleInstallModpack(modpackData) {
    if (!modpackData) return
    showModpackBrowser.value = false
    pendingModpackInstall.value = modpackData
    showModpackInstallConfirmModal.value = true
  }

  function cancelModpackInstallConfirmation() {
    showModpackInstallConfirmModal.value = false
    pendingModpackInstall.value = null
    modpackCreateBackup.value = true
  }

  async function fetchModpackProgress() {
    try {
      const progress = await getModpackInstallProgress(currentServerId.value)
      modpackProgress.value = progress?.active ? progress : null
    } catch {
      // polling failure is non-critical — silently swallow
    }
  }

  function clearModpackProgress() {
    modpackProgress.value = null
  }

  async function runModpackInstall(modpackData) {
    if (!modpackData) return
    const isRetry = Boolean(modpackData.allowMissing || modpackData.modSideOverrides)
    modpackInstalling.value = true
    if (isRetry) {
      pendingModpackInstall.value = modpackData
      showModpackInstallConfirmModal.value = true
    }
    try {
      // An uploaded .mrpack (#53) is already staged on the backend, so it is
      // installed by upload id rather than resolved from a Modrinth project.
      // The missing-files retry reuses the same staged archive, which is why
      // the backend only discards it once an install actually succeeds.
      const result = modpackData.uploadId
        ? await installUploadedModpack(modpackData.uploadId, {
          server_id: currentServerId.value,
          loader: modpackData.loader,
          clean_install: !isRetry,
          create_backup: isRetry ? false : modpackData.createBackup,
          allow_missing: Boolean(modpackData.allowMissing),
          mod_side_overrides: modpackData.modSideOverrides || null,
          force: Boolean(modpackData.force)
        })
        : await installModpack(modpackData.projectId, {
          mc_version: modpackData.mcVersion,
          loader: modpackData.loader,
          server_id: currentServerId.value,
          clean_install: !isRetry,
          create_backup: isRetry ? false : modpackData.createBackup,
          allow_missing: Boolean(modpackData.allowMissing),
          mod_side_overrides: modpackData.modSideOverrides || null
        })
      showModpackBrowser.value = false
      showModpackInstallConfirmModal.value = false
      pendingModpackInstall.value = null
      modpackCreateBackup.value = true
      const cleanedCount = Array.isArray(result?.cleaned_paths) ? result.cleaned_paths.length : 0
      const missingCount = Array.isArray(result?.missing_files) ? result.missing_files.length : 0
      const skippedCount = Array.isArray(result?.files_skipped) ? result.files_skipped.length : 0
      const uncertainCount = Array.isArray(result?.uncertain_mod_files) ? result.uncertain_mod_files.length : 0
      const cleanedNote = ` Replaced folders: ${cleanedCount}.`
      const missingNote = missingCount ? ` Missing files skipped: ${missingCount}.` : ''
      const skippedNote = skippedCount ? ` Skipped ${skippedCount} client-only mod${skippedCount === 1 ? '' : 's'}.` : ''
      const uncertainNote = uncertainCount ? ` Installed ${uncertainCount} mod${uncertainCount === 1 ? '' : 's'} with unknown server compatibility.` : ''
      const backupNote = result?.backup_file ? ` Backup: ${result.backup_file}.` : ''
      toast.success(`${modpackData.title} installed successfully.${cleanedNote}${missingNote}${skippedNote}${uncertainNote}${backupNote}`, 'Modpack Installed')
      if (uncertainCount) {
        toast.warning('Unknown-side mods were kept because missing metadata is not evidence they are client-only. Check server logs if startup fails.', 'Compatibility Warning')
      }
      if (result?.java_warning) toast.warning(result.java_warning.message, 'Java Version Mismatch')
      await Promise.all([loadServer({ silent: true }), loadMods()])
    } catch (error) {
      const uncertainMods = error?.data?.uncertain_mod_files
      const canContinueWithUncertain = Boolean(error?.data?.can_continue_with_uncertain)
      if (error?.status === 409 && canContinueWithUncertain && Array.isArray(uncertainMods) && uncertainMods.length) {
        showModpackInstallConfirmModal.value = false
        pendingUncertainModpackData.value = modpackData
        uncertainModsReport.value = uncertainMods
        showUncertainModsModal.value = true
        toast.warning('Some mods need a server/client decision before install can continue.', 'Uncertain Mod Side')
        return
      }
      const missingFiles = error?.data?.missing_files
      const canContinue = Boolean(error?.data?.can_continue_with_missing)
      if (!modpackData.allowMissing && error?.status === 409 && canContinue && Array.isArray(missingFiles) && missingFiles.length) {
        showModpackInstallConfirmModal.value = false
        pendingMissingModsInstall.value = { ...modpackData, allowMissing: true }
        missingModsReport.value = missingFiles
        showMissingModsConfirmModal.value = true
        toast.warning(`${missingFiles.length} files could not be downloaded. Choose if you want to continue without them.`, 'Missing Modpack Files')
        return
      }
      showModpackInstallConfirmModal.value = false
      console.error('Modpack install failed:', error)
      toast.error(error.message || 'Modpack installation failed', 'Installation Failed')
    } finally {
      modpackInstalling.value = false
    }
  }

  async function confirmModpackInstall() {
    const data = pendingModpackInstall.value
    if (!data) return
    await runModpackInstall({ ...data, createBackup: modpackCreateBackup.value, allowMissing: false })
  }

  function cancelMissingModsConfirmation() {
    showMissingModsConfirmModal.value = false
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
  }

  async function confirmInstallWithMissingMods() {
    const data = pendingMissingModsInstall.value
    if (!data) return
    showMissingModsConfirmModal.value = false
    await runModpackInstall(data)
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
  }

  function cancelUncertainModsDecision() {
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    toast.info('Modpack install canceled. Unknown mod sides were not confirmed.', 'Install Canceled')
  }

  async function confirmUncertainModsDecision(overrides) {
    const data = pendingUncertainModpackData.value
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    if (!data) return
    await runModpackInstall({ ...data, modSideOverrides: overrides || {} })
  }

  function handleRemoveMod(mod) {
    modToRemove.value = mod
    confirmModalData.value = {
      title: 'Remove Mod',
      message: `Remove ${mod.name}?`,
      description: 'This will delete the mod file from the server. This action cannot be undone.',
      type: 'danger',
      confirmText: 'Remove',
      cancelText: 'Cancel'
    }
    showConfirmModal.value = true
  }

  async function confirmRemoveMod() {
    if (!modToRemove.value) return
    if (modToRemove.value === '__bulk__') {
      await confirmBulkRemoveMods()
      return
    }
    const filename = modToRemove.value.filename || modToRemove.value.name
    try {
      await removeMod(currentServerId.value, filename)
      // Drop cache entry so re-list doesn't show stale metadata if a
      // different jar with the same filename ever lands later.
      invalidateModrinthMetaCache(filename)
      toast.success(`${modToRemove.value.name} removed`, 'Mod Removed')
      await loadMods()
    } catch (error) {
      console.error('Failed to remove mod:', error)
      toast.error('Failed to remove mod', 'Error')
    } finally {
      showConfirmModal.value = false
      modToRemove.value = null
    }
  }

  function cancelRemoveMod() {
    showConfirmModal.value = false
    if (modToRemove.value === '__bulk__') {
      selectedModPaths.value = new Set()
    }
    modToRemove.value = null
  }

  function toggleModSelection(mod) {
    const next = new Set(selectedModPaths.value)
    if (next.has(mod.path)) {
      next.delete(mod.path)
    } else {
      next.add(mod.path)
    }
    selectedModPaths.value = next
  }

  function toggleSelectAllMods() {
    if (allFilteredSelected.value) {
      const next = new Set(selectedModPaths.value)
      filteredMods.value.forEach((m) => next.delete(m.path))
      selectedModPaths.value = next
    } else {
      const next = new Set(selectedModPaths.value)
      filteredMods.value.forEach((m) => next.add(m.path))
      selectedModPaths.value = next
    }
  }

  function clearModSelection() {
    selectedModPaths.value = new Set()
  }

  function handleBulkRemoveMods() {
    if (selectedCount.value === 0) return
    const n = selectedCount.value
    confirmModalData.value = {
      title: 'Remove Mods',
      message: `Remove ${n} selected mod${n === 1 ? '' : 's'}?`,
      description: 'This will permanently delete the selected mod files from the server. This action cannot be undone.',
      type: 'danger',
      confirmText: `Remove ${n} mod${n === 1 ? '' : 's'}`,
      cancelText: 'Cancel'
    }
    modToRemove.value = '__bulk__'
    showConfirmModal.value = true
  }

  async function confirmBulkRemoveMods() {
    const paths = new Set(selectedModPaths.value)
    const mods = installedMods.value.filter((m) => paths.has(m.path))
    const filenames = mods.map((m) => m.filename || m.name)
    if (!filenames.length) {
      showConfirmModal.value = false
      modToRemove.value = null
      return
    }
    bulkDeleting.value = true
    try {
      await bulkRemoveMods(currentServerId.value, filenames)
      for (const fn of filenames) {
        invalidateModrinthMetaCache(fn)
      }
      toast.success(`${filenames.length} mod${filenames.length === 1 ? '' : 's'} removed`, 'Mods Removed')
      await loadMods()
    } catch (error) {
      console.error('Failed to bulk remove mods:', error)
      toast.error('Failed to remove selected mods', 'Error')
    } finally {
      // F9: clear selection in finally — success AND failure both invalidate
      // the previous selection (some mods may have been deleted on the
      // server before an error mid-batch). User re-selects from fresh state.
      selectedModPaths.value = new Set()
      bulkDeleting.value = false
      showConfirmModal.value = false
      modToRemove.value = null
    }
  }

  async function performServerAction(action, fn, successMessage) {
    if (actionState.value[action]) return
    actionState.value[action] = true
    try {
      const result = await fn(currentServerId.value)
      if (result.success) {
        toast.success(successMessage, 'Server Updated')
      } else {
        toast.error(result.message || 'Operation failed', 'Server Error')
      }
    } catch (error) {
      console.error(`Failed to ${action} server:`, error)
      if ((action === 'start' || action === 'restart') && (error.data?.java_missing || error.data?.java_too_old)) {
        pendingJavaAction.value = action
        showJavaModal.value = true
      } else {
        toast.error(error.message || `Failed to ${action} server`, 'Server Error')
      }
    } finally {
      actionState.value[action] = false
      await loadServer()
      if (action === 'start' || action === 'restart') {
        await loadLogs()
      }
    }
  }

  function handleStart() { return performServerAction('start', startServer, 'Server start requested') }
  function handleStop()  { return performServerAction('stop',  stopServer,  'Server stop requested') }
  function handleRestart() { return performServerAction('restart', restartServer, 'Server restart requested') }

  async function handleInstall() {
    if (actionState.value.install || !server.value) return
    actionState.value.install = true
    // Pin the id at the start: the poll must follow the server this install
    // was launched for, not whichever server the user later navigates to.
    // Reading currentServerId.value each iteration made a mid-install switch
    // poll the wrong server, break early, and toast a false failure.
    const installServerId = currentServerId.value
    try {
      // 202 + initial progress; the real outcome arrives via polling — the
      // create modal's exact contract (750ms cadence, terminal on !active
      // or done/failed; 'aborted' terminates via active:false).
      await installServer(installServerId)
      let progress = null
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, 750))
        progress = await getServerInstallProgress(installServerId)
        if (!progress.active || progress.phase === 'done' || progress.phase === 'failed') break
      }
      if (progress.phase === 'done') {
        toast.success('Server installed successfully.', 'Server Installation')
      } else {
        toast.error(progress.error || 'Installation failed', 'Server Installation')
      }
    } catch (error) {
      console.error('Failed to install server:', error)
      if (error.data?.java_missing || error.data?.java_too_old) {
        // The backend's Java-guard 400 already cleared the install-progress
        // marker, so the retry via the Java modal is unblocked. No polling
        // on this path.
        pendingJavaAction.value = 'install'
        showJavaModal.value = true
      } else {
        toast.error(error.message || 'Failed to install server', 'Server Error')
      }
    } finally {
      actionState.value.install = false
      await loadServer()
    }
  }

  function handleJavaInstalled() {
    const action = pendingJavaAction.value
    showJavaModal.value = false
    pendingJavaAction.value = null
    if (action === 'install') handleInstall()
    else if (action === 'restart') handleRestart()
    else handleStart()
  }

  // Step back toward older commands (ArrowUp). Entering recall stashes the
  // current draft; once at the oldest entry, further presses stay put.
  function recallPreviousCommand() {
    if (!commandHistory.value.length) return
    if (historyIndex.value === null) {
      historyDraft.value = consoleCommand.value
      historyIndex.value = commandHistory.value.length - 1
    } else if (historyIndex.value > 0) {
      historyIndex.value -= 1
    }
    consoleCommand.value = commandHistory.value[historyIndex.value]
  }

  // Step back toward newer commands (ArrowDown). Moving past the newest entry
  // leaves recall and restores the stashed draft, matching shell behaviour.
  function recallNextCommand() {
    if (historyIndex.value === null) return
    if (historyIndex.value < commandHistory.value.length - 1) {
      historyIndex.value += 1
      consoleCommand.value = commandHistory.value[historyIndex.value]
    } else {
      historyIndex.value = null
      consoleCommand.value = historyDraft.value
      historyDraft.value = ''
    }
  }

  async function sendConsoleCommand() {
    if (!canSendCommand.value || !consoleCommand.value.trim()) return
    const command = consoleCommand.value.trim()
    commandSending.value = true
    try {
      await sendServerCommand(currentServerId.value, command)
      toast.success('Command sent to server', 'Console')
      // Record only on success: a failed send leaves the text in the input for
      // the user to retry, so adding it here would duplicate that line.
      // Consecutive repeats collapse the way shells dedupe them.
      if (commandHistory.value[commandHistory.value.length - 1] !== command) {
        commandHistory.value.push(command)
        if (commandHistory.value.length > MAX_COMMAND_HISTORY) commandHistory.value.shift()
      }
      historyIndex.value = null
      historyDraft.value = ''
      consoleCommand.value = ''
      await loadLogs()
    } catch (error) {
      console.error('Failed to send command:', error)
      toast.error('Failed to send console command', 'Console Error')
    } finally {
      commandSending.value = false
    }
  }

  async function handleSaveSettings(settings) {
    if (!server.value) return
    try {
      const updated = await updateServerSettings(currentServerId.value, settings)
      server.value = updated
      serverSettings.value = defaultSettings(updated)
      await loadServers()
      toast.success('Settings saved successfully', 'Settings Updated')
    } catch (error) {
      console.error('Failed to save settings:', error)
      toast.error(error.message || 'Failed to save settings', 'Error')
    }
  }

  function resetSettings() {
    if (!server.value) return
    serverSettings.value = defaultSettings(server.value)
  }

  // Boot auto-start mode is a Fabricator-level preference (not server.properties),
  // so it saves instantly via its own endpoint and is editable while running —
  // independent of the main settings form and its "stop to edit" guard.
  const autoStartMode = computed(() => server.value?.autoStart || 'never')

  async function setAutoStartMode(mode) {
    if (!server.value) return
    const previous = server.value.autoStart || 'never'
    if (mode === previous) return
    server.value = { ...server.value, autoStart: mode }  // optimistic
    try {
      await setServerAutoStart(currentServerId.value, mode)
      toast.success('Auto-start updated', 'Settings')
    } catch (error) {
      server.value = { ...server.value, autoStart: previous }  // rollback
      toast.error(error.message || 'Failed to update auto-start', 'Error')
    }
  }

  // Performs the same job as the layout's previous resetDashboardState().
  // setup-syntax Pinia stores have no automatic $reset, so we write it explicitly.
  function resetState() {
    server.value = null
    serverSettings.value = null
    installedMods.value = []
    logs.value = { stdout: [], stderr: [], running: false }
    fileBrowser.value = { currentPath: '', entries: [], loading: false, error: null }
    fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: null }
    modSearch.value = ''
    modToRemove.value = null
    selectedModPaths.value = new Set()
    bulkDeleting.value = false
    serverLoading.value = true
    modsLoading.value = false
    logsLoading.value = false
    installLoading.value = false
    modpackInstalling.value = false
    modpackProgress.value = null
    showModpackInstallConfirmModal.value = false
    showMissingModsConfirmModal.value = false
    pendingModpackInstall.value = null
    modpackCreateBackup.value = true
    pendingMissingModsInstall.value = null
    missingModsReport.value = []
    showUncertainModsModal.value = false
    uncertainModsReport.value = []
    pendingUncertainModpackData.value = null
    actionState.value = { start: false, stop: false, restart: false, install: false }
    showModBrowser.value = false
    showJavaModal.value = false
    pendingJavaAction.value = null
    showModpackBrowser.value = false
    showConfirmModal.value = false
    confirmModalData.value = {}
    consoleCommand.value = ''
    commandSending.value = false
    // Scoped per server — one server's command history must not surface in
    // another's console after a switch.
    commandHistory.value = []
    historyIndex.value = null
    historyDraft.value = ''
    showDeleteServerModal.value = false
    deletingServer.value = false
  }

  return {
    // State
    currentServerId,
    currentRouteName,
    serversList,
    server,
    serverLoading,
    modsLoading,
    logsLoading,
    installedMods,
    modSearch,
    logs,
    serverSettings,
    showModBrowser,
    showVersionPicker,
    versionPickerMod,
    showJavaModal,
    pendingJavaAction,
    showModpackBrowser,
    showConfirmModal,
    confirmModalData,
    modToRemove,
    selectedModPaths,
    bulkDeleting,
    installLoading,
    modpackInstalling,
    actionState,
    consoleCommand,
    commandSending,
    commandHistory,
    fileBrowser,
    fileEditor,
    fileSearch,
    showDeleteServerModal,
    deletingServer,
    modpackProgress,
    showModpackInstallConfirmModal,
    pendingModpackInstall,
    modpackCreateBackup,
    showMissingModsConfirmModal,
    pendingMissingModsInstall,
    missingModsReport,
    showUncertainModsModal,
    uncertainModsReport,
    pendingUncertainModpackData,
    // Getters
    modpackProgressLabel,
    modpackProgressPercent,
    serverStatus,
    canEditSettings,
    ramMetrics,
    filteredMods,
    selectedCount,
    allFilteredSelected,
    playersDisplay,
    statusLabel,
    startLocked,
    startButtonLabel,
    activeModpack,
    isInstalling,
    canSendCommand,
    missingModsDescriptionText,
    hasFileChanges,
    isDirtySettings,
    // Actions
    closeModBrowser,
    openVersionPicker,
    closeVersionPicker,
    handleSelectVersion,
    closeModpackBrowser,
    closeJavaModal,
    setConsoleCommand,
    recallPreviousCommand,
    recallNextCommand,
    loadServers,
    loadServer,
    loadMods,
    loadLogs,
    refreshAll,
    openFileBrowser,
    enterFileEntry,
    goUpDirectory,
    searchFiles,
    clearFileSearch,
    revealSearchHit,
    openFile,
    saveFile,
    closeFile,
    openModBrowser,
    openModpackBrowser,
    openDeleteServerModal,
    cancelDeleteServer,
    confirmDeleteServer,
    goToConsole,
    goToFiles,
    goToBackups,
    goToSettings,
    goToMods,
    handleInstallMod,
    handleInstallModpack,
    cancelModpackInstallConfirmation,
    fetchModpackProgress,
    clearModpackProgress,
    runModpackInstall,
    confirmModpackInstall,
    cancelMissingModsConfirmation,
    confirmInstallWithMissingMods,
    cancelUncertainModsDecision,
    confirmUncertainModsDecision,
    handleRemoveMod,
    confirmRemoveMod,
    cancelRemoveMod,
    toggleModSelection,
    toggleSelectAllMods,
    clearModSelection,
    handleBulkRemoveMods,
    handleStart,
    handleInstall,
    handleStop,
    handleRestart,
    handleJavaInstalled,
    sendConsoleCommand,
    handleSaveSettings,
    resetSettings,
    autoStartMode,
    setAutoStartMode,
    resetState
  }
})
