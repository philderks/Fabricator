import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { useRouter } from 'vue-router'
import {
  checkModUpdates,
  installMod,
  installModpack,
  installUploadedModpack,
  getModpackInstallProgress
} from '../api/modrinth'
import {
  getServer,
  getServers,
  reorderServers,
  getInstalledMods,
  removeMod,
  bulkRemoveMods,
  setModsEnabled,
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
  saveServerFile,
  uploadServerFile,
  deleteServerFiles,
  createServerFolder
} from '../api/servers'
import { useToast } from '../composables/useToast'
import { usePreferencesStore } from './preferences'
import { t } from '../i18n'
import {
  enrichInstalledModsWithModrinth,
  invalidateModrinthMetaCache
} from '../utils/enrichInstalledModsModrinth'
import { installedModDisplayName } from '../utils/installedModDisplay'
import { installedEntryMatchesProjectRef } from '../utils/modrinthJarMatch'
import { normalizeMotd } from '../utils/motd'
// Status-display logic consolidated in utils/getEffectiveStatus (F6/CC5);
// keep alias for the existing call sites in this file.
import { getEffectiveStatus as pickEffectiveStatus } from '../utils/getEffectiveStatus'
import {
  createProgressPoller,
  lostContactMessage,
  POLL_INTERVAL_MS
} from '../utils/pollProgress'

// Values are i18n keys, translated where the label is built.
const MODPACK_STAGE_LABELS = {
  starting: 'install.modpackStages.starting',
  resolving: 'install.modpackStages.resolving',
  cleaning: 'install.modpackStages.cleaning',
  downloading_pack: 'install.modpackStages.downloadingPack',
  checking_availability: 'install.modpackStages.checkingAvailability',
  installing_files: 'install.modpackStages.installingFiles',
  extracting_overrides: 'install.modpackStages.extractingOverrides',
  verifying_mod_sides: 'install.modpackStages.verifyingModSides',
  done: 'install.modpackStages.done'
}

// Loader-install phases, from backend/server/install_progress.py. The pack's
// own stages are MODPACK_STAGE_LABELS above; these cover the stretch between
// resolving a pack and installing it, which is still part of the same job.
const INSTALL_PHASE_LABELS = {
  starting: 'install.phases.starting',
  resolving_modpack: 'install.phases.resolvingModpack',
  resolving_versions: 'install.phases.resolvingVersions',
  downloading_installer: 'install.phases.downloadingInstaller',
  downloading_server_jar: 'install.phases.downloadingServerJar',
  verifying: 'install.phases.verifying',
  running_installer: 'install.phases.runningInstaller',
  detecting_artifacts: 'install.phases.finishing',
  writing_eula: 'install.phases.finishing'
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

// Relative paths come off the backend with the host's separator, so a Windows
// install reports `mods\\a.jar` where Linux reports `mods/a.jar`. Normalise
// before comparing, or deleting a folder wouldn't close the file open beneath it.
function isPathInside(childPath, ancestorPath) {
  const child = String(childPath || '').replace(/\\/g, '/')
  const ancestor = String(ancestorPath || '').replace(/\\/g, '/')
  if (!child || !ancestor) return false
  return child === ancestor || child.startsWith(`${ancestor}/`)
}

export const useServerStore = defineStore('server', () => {
  const router = useRouter()
  const toast = useToast()
  const prefs = usePreferencesStore()

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
  // Bumped whenever an icon changes, and put on every icon URL: the browser
  // reuses an image it already decoded for the same URL, so without it the
  // switcher and the overview would keep showing the old icon.
  const iconVersion = ref(Date.now())
  const iconUrlFor = (id) => `/api/servers/${id}/icon?v=${iconVersion.value}`
  const iconChanged = () => { iconVersion.value = Date.now() }
  const showModBrowser = ref(false)
  const showJavaModal = ref(false)
  const pendingJavaAction = ref(null)
  const showModpackBrowser = ref(false)
  const showConfirmModal = ref(false)
  const confirmModalData = ref({})
  const modToRemove = ref(null)
  const selectedModPaths = ref(new Set())
  const bulkDeleting = ref(false)
  const togglingMods = ref(false)
  // filename -> { projectId, versionId, versionNumber } for jars with a newer
  // compatible release (#80).
  const modUpdates = ref({})
  // [{ projectId, slug, title }] required by those updates and not installed.
  const modUpdateDeps = ref([])
  const updatingMods = ref(false)
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
  // Progress for a pack the *install worker* is applying, as opposed to
  // modpackProgress above which only covers an install this tab started from
  // the Mods browser. A pack chosen in the create modal is installed by the
  // same worker that installs the loader, so by the time the user reaches the
  // server its mods are still downloading with nothing in this tab aware of it.
  // Sourced from GET /servers/<id>/install/progress.
  const serverInstallProgress = ref(null)
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
    name: data.name || t('servers.defaultName'),
    port: data.port ?? 25565,
    serverIp: data.serverIp || '',
    // Normalized for the baseline too, so an old escaped MOTD isn't "dirty".
    // Only a missing MOTD gets the default: an empty one is a valid choice
    // (Minecraft shows nothing), not something to paper over.
    motd: data.motd == null ? t('servers.defaultMotd') : normalizeMotd(data.motd),
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
    memoryMin: data.memoryMin ?? data.memory ?? 4,
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
    const suffix = remaining > 0 ? `\n${t('modpacks.missingFilesMore', { n: remaining })}` : ''
    return `${t('modpacks.missingFilesIntro')}\n${preview}${suffix}\n\n${t('modpacks.missingFilesQuestion')}`
  }

  // ---------- Computeds (getters) ----------

  // Both progress sources describe the same install with the same stage
  // vocabulary, so the phrasing lives here once rather than per surface.
  function stageLabel(p) {
    const key = MODPACK_STAGE_LABELS[p.stage]
    const stage = key ? t(key) : (p.stage || t('common.working'))
    if (p.stage === 'installing_files' && p.total > 0) {
      return t('install.stageProgress', { label: stage, current: p.current, total: p.total })
    }
    return stage
  }

  function stagePercent(p) {
    if (!p.total) return 0
    return Math.round((p.current / p.total) * 100)
  }

  const modpackProgressLabel = computed(() => {
    const p = modpackProgress.value
    if (!p?.active) return ''
    return stageLabel(p)
  })

  const modpackProgressPercent = computed(() => {
    const p = modpackProgress.value
    if (!p?.active) return 0
    return stagePercent(p)
  })

  // One flattened view of whatever the install worker is doing, whether that is
  // the loader's half of the job or a pack's. A create-time install runs as a
  // single worker — resolve the pack, install the loader, install the pack —
  // and only the last step reports the pack's own stage/counts (under
  // modpack_*-prefixed keys, since the entry is shared with the loader's
  // phases), so this hides that split from every surface that renders it.
  const installActivity = computed(() => {
    const p = serverInstallProgress.value
    if (!p?.active) return null

    if (p.phase === 'installing_modpack') {
      const inner = {
        stage: p.modpack_stage || '',
        current: p.modpack_current || 0,
        total: p.modpack_total || 0
      }
      return {
        kind: 'modpack',
        name: p.modpack_name || '',
        label: stageLabel(inner),
        percent: stagePercent(inner),
        determinate: inner.total > 0,
        detail: p.modpack_detail || ''
      }
    }

    // Loader phases. Only the two download phases actually emit bytes, and the
    // progress entry merges keys rather than replacing them — so bytes_done
    // lingers at 100% into later phases. Trusting it there would park a full
    // bar over running_installer, which for Forge/NeoForge is the long part.
    const hasBytes = p.phase === 'downloading_installer' || p.phase === 'downloading_server_jar'
    const done = Number(p.bytes_done) || 0
    const total = hasBytes ? (Number(p.bytes_total) || 0) : 0
    return {
      kind: 'loader',
      name: p.modpack_name || '',
      label: INSTALL_PHASE_LABELS[p.phase] ? t(INSTALL_PHASE_LABELS[p.phase]) : t('install.installingServer'),
      percent: total > 0 ? Math.round((done / total) * 100) : 0,
      determinate: total > 0,
      detail: ''
    }
  })

  // Falls back to the persisted status so the install is still announced when
  // no progress entry exists: the worker's progress lives in memory on the
  // backend, so a restart mid-install wipes it while the record stays
  // 'installing'. An unlabelled "installing" beats a page of zeroes.
  const serverInstalling = computed(() =>
    installActivity.value !== null || pickEffectiveStatus(server.value) === 'installing'
  )

  // Always renderable while serverInstalling is true, including the
  // restart-wiped-the-progress case above, where all we know is that it runs.
  const installDisplay = computed(() => installActivity.value || {
    kind: 'loader',
    name: '',
    label: t('install.installingServer'),
    percent: 0,
    determinate: false,
    detail: ''
  })

  // The Mods tab's narrower view: only surface an install there when a pack is
  // actually part of it. Gated on the server record rather than the phase —
  // the pack's phases bookend the loader's, so keying off them alone would pull
  // the panel for the whole middle stretch and put it back afterwards.
  // pendingModpack is written before the worker starts and cleared once the
  // pack lands, so it covers the install end to end; the phase check is the
  // fallback for the window before the record has loaded.
  const backgroundModpack = computed(() => {
    const activity = installActivity.value
    if (!activity) return null
    if (!server.value?.pendingModpack && activity.kind !== 'modpack') return null
    return activity
  })

  const backgroundModpackInstalling = computed(() => backgroundModpack.value !== null)
  const backgroundModpackLabel = computed(() => backgroundModpack.value?.label || '')
  const backgroundModpackPercent = computed(() => backgroundModpack.value?.percent || 0)

  const serverStatus = computed(() => {
    const loaderName = server.value?.loader
      ? server.value.loader.charAt(0).toUpperCase() + server.value.loader.slice(1)
      : t('common.unknown')

    return {
      name: server.value?.name || t('servers.defaultName'),
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
      tps: server.value?.runtime?.tps ?? null,
      // Absent (stopped, or a backend that predates TPS sampling) reads as
      // supported, so the card falls back to the plain "no reading yet" dash
      // rather than claiming the server can't report one.
      tpsSupported: server.value?.runtime?.tpsSupported !== false
    }
  })

  const canEditSettings = computed(() => serverStatus.value.status !== 'running')

  const ramMetrics = computed(() => {
    const runtimeRam = server.value?.runtime?.ram
    // Configured maximum heap. This is used as a fallback while stopped or
    // before the JVM has reported its runtime heap statistics
    const configuredUnit = server.value?.memoryUnit ?? serverSettings.value?.memoryUnit ?? 'GB'
    const configuredValue = Number(server.value?.memory ?? serverSettings.value?.memory ?? 0)
    const configuredMax = configuredUnit === 'MB' ? configuredValue / 1024 : configuredValue

    const toGB = (bytes) =>
      typeof bytes === 'number' && Number.isFinite(bytes)
        ? bytes / (1024 ** 3)
        : null

    const runtimeHeapMax = toGB(runtimeRam?.heapMaxBytes)

    return {
      heapUsed: toGB(runtimeRam?.heapUsedBytes),
      heapCommitted: toGB(runtimeRam?.heapCommittedBytes),
      heapMax: runtimeHeapMax !== null && runtimeHeapMax > 0
        ? runtimeHeapMax
        : configuredMax > 0
          ? configuredMax
          : null,
      rss: toGB(runtimeRam?.rssBytes),
      running: serverStatus.value.status === 'running'
    }
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

  const selectedMods = computed(() => installedMods.value.filter((m) => selectedModPaths.value.has(m.path)))
  const selectedEnabledCount = computed(() => selectedMods.value.filter((m) => !m.disabled).length)
  const selectedDisabledCount = computed(() => selectedMods.value.length - selectedEnabledCount.value)

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
    if (s === 'running') return t('status.running')
    if (s === 'stopped') return t('status.stopped')
    if (s === 'pending') return t('status.pending')
    if (s === 'installing') return t('status.installing')
    if (s === 'failed') return t('status.failed')
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : t('status.unknown')
  })

  const startLocked = computed(() => serverStatus.value.status === 'installing')

  const startButtonLabel = computed(() => {
    if (serverStatus.value.status === 'installing') return t('topbar.installing')
    if (serverStatus.value.status === 'pending') {
      return actionState.value.install ? t('topbar.installing') : t('common.install')
    }
    return actionState.value.start ? t('topbar.starting') : t('topbar.start')
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

  // The MOTD as saved (and so as players see it), by the same rules as the
  // settings form, unsaved edits aside.
  const savedMotd = computed(() => (server.value ? defaultSettings(server.value).motd : ''))

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

  /** Persist the current `serversList` order (#84) — the switcher reorders
   *  the list locally while dragging and saves once on drop. A failed save
   *  reloads the real order. */
  async function saveServerOrder() {
    try {
      await reorderServers(serversList.value.map((s) => s.id))
    } catch (error) {
      console.error('Failed to reorder servers:', error)
      toast.error(t('servers.orderSaveFailed'), t('common.error'))
      loadServers()
    }
  }

  async function loadServer(options = {}) {
    const { silent = false } = options
    if (!silent) serverLoading.value = true
    try {
      const data = await getServer(currentServerId.value, { heap: prefs.showHeapStats })
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
      toast.error(t('servers.detailsLoadFailed'), t('common.error'))
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
          version: recorded?.versionNumber || file.version || t('mods.localVersion'),
          downloads: file.downloads || 'N/A',
          size: file.size,
          updatedAt: file.updatedAt,
          path: file.path,
          disabled: /\.jar\.disabled$/i.test(file.name),
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
      // Not awaited: the list is usable before the update check answers.
      loadModUpdates()
    } catch (error) {
      console.error('Failed to load mods:', error)
      toast.error(t('mods.loadFailed'), t('common.error'))
    } finally {
      modsLoading.value = false
    }
  }

  async function loadModUpdates() {
    const id = currentServerId.value
    try {
      const { updates, dependencies } = await checkModUpdates(id)
      // Ignore a late answer for a server the user has since left.
      if (id !== currentServerId.value) return
      modUpdates.value = updates || {}
      modUpdateDeps.value = dependencies || []
    } catch {
      // Offline or rate limited: just no update button this time.
    }
  }

  /** Dependencies the updates need that no installed jar provides. The
   *  backend matched by hash and manifest; the filename check here also
   *  catches a hand-added jar Modrinth doesn't know. */
  const missingUpdateDeps = computed(() =>
    modUpdateDeps.value.filter((dep) => !installedMods.value.some((mod) =>
      installedEntryMatchesProjectRef(mod, { id: dep.projectId, slug: dep.slug })
    ))
  )

  function updateAllMods() {
    const entries = Object.entries(modUpdates.value)
    if (!entries.length || updatingMods.value) return
    const n = entries.length
    const deps = missingUpdateDeps.value
    const byFilename = new Map(installedMods.value.map((m) => [m.filename, m]))
    confirmModalData.value = {
      title: t('mods.update.title'),
      message: t('mods.update.message', n),
      description: deps.length
        ? t('mods.update.depsDescription', deps.length)
        : t('mods.update.description'),
      type: 'info',
      confirmText: t('mods.updateMods', n),
      cancelText: t('common.cancel'),
      items: [
        ...entries.map(([filename, u]) => {
          const mod = byFilename.get(filename)
          return `${mod ? installedModDisplayName(mod) : filename}: ${mod?.version || '?'} → ${u.versionNumber}`
        }),
        ...deps.map((d) => t('mods.update.newDependency', { title: d.title }))
      ]
    }
    modToRemove.value = '__update__'
    showConfirmModal.value = true
  }

  /**
   * Install missing dependencies, then update every mod, one install at a
   * time. Each update is a replace-install, so a failed download leaves that
   * mod on its old version. `pin: false` keeps updated mods eligible for the
   * next update-all.
   */
  async function confirmUpdateAllMods() {
    showConfirmModal.value = false
    modToRemove.value = null
    const entries = Object.entries(modUpdates.value)
    if (!entries.length || !server.value || updatingMods.value) return
    updatingMods.value = true
    // Captured up front: the user may switch servers while this runs.
    const target = { id: currentServerId.value, version: server.value.version, loader: server.value.loader }
    const base = { mc_version: target.version, loader: target.loader, server_id: target.id }
    const jobs = [
      // Dependencies first, as a single install does: newest compatible release.
      ...missingUpdateDeps.value.map((dep) => ({
        label: dep.title,
        run: () => installMod(dep.projectId, base)
      })),
      ...entries.map(([filename, update]) => ({
        label: filename,
        run: async () => {
          await installMod(update.projectId, {
            ...base, version_id: update.versionId, replaces: filename, pin: false
          })
          invalidateModrinthMetaCache(filename)
        }
      }))
    ]
    const failed = []
    for (const job of jobs) {
      try {
        await job.run()
      } catch (error) {
        console.error(`Update failed for ${job.label}:`, error)
        failed.push(job.label)
      }
    }
    const done = jobs.length - failed.length
    if (done) toast.success(t('mods.update.done', done), t('mods.update.doneTitle'))
    if (failed.length) toast.error(t('mods.update.failed', { list: failed.join(', ') }), t('mods.update.failedTitle'))
    updatingMods.value = false
    if (target.id === currentServerId.value) await loadMods()
  }

  async function loadLogs(limit = 1000) {
    if (!server.value || logsLoading.value) return
    logsLoading.value = true
    try {
      logs.value = await getServerLogs(currentServerId.value, { limit })
    } catch (error) {
      console.error('Failed to load logs:', error)
      toast.error(t('console.logsLoadFailed'), t('common.error'))
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
      fileBrowser.value = { currentPath: path, entries: [], loading: false, error: error.message || t('files.loadFailed') }
    }
  }

  function enterFileEntry(entry) {
    if (entry.isDir) openFileBrowser(entry.relativePath)
  }

  // Per-file upload rows the Files page renders as a progress list. Keyed by a
  // local id rather than the filename so two uploads of the same name (a retry
  // after a replace prompt, say) stay distinct rows.
  const fileUploads = ref([])
  let uploadRowId = 0

  function clearFinishedUploads() {
    fileUploads.value = fileUploads.value.filter((row) => row.status === 'uploading')
  }

  function cancelUpload(id) {
    const row = fileUploads.value.find((entry) => entry.id === id)
    row?.abort?.()
  }

  /**
   * Upload files into the folder currently open in the browser.
   *
   * Sequential rather than parallel: a handful of large jars over a home
   * upstream link finish sooner one at a time than interleaved, and one
   * moving progress bar reads better than six stalled ones.
   *
   * Returns the names that hit an existing file so the caller can offer to
   * replace them — the backend refuses by default rather than clobbering.
   */
  async function uploadFiles(files, { overwrite = false } = {}) {
    const list = Array.from(files || [])
    if (!list.length) return { uploaded: [], conflicts: [] }

    const dirPath = fileBrowser.value.currentPath || ''
    const uploaded = []
    const conflicts = []

    for (const file of list) {
      const row = reactive({
        id: ++uploadRowId,
        name: file.name,
        pct: 0,
        status: 'uploading',
        error: null,
        abort: null,
      })
      fileUploads.value = [...fileUploads.value, row]

      try {
        await uploadServerFile(currentServerId.value, dirPath, file, {
          overwrite,
          onProgress: (pct) => { row.pct = pct },
          registerAbort: (abort) => { row.abort = abort },
        })
        row.status = 'done'
        uploaded.push(file.name)
      } catch (error) {
        row.error = error?.message || t('files.uploadFailed')
        if (error?.status === 409 && error?.data?.code === 'file-exists') {
          // Not a failure the user has to read: the replace prompt takes this
          // file over from here. Marking it 'failed' would leave a red "already
          // exists" row standing after a successful Replace — and because the
          // filter below keeps failures, it would outlive every later upload.
          row.status = 'conflict'
          conflicts.push(file)
        } else {
          row.status = 'failed'
          if (error?.message !== t('errors.uploadCancelled')) {
            toast.error(`${file.name}: ${row.error}`, t('nav.files'))
          }
        }
      }
    }

    if (uploaded.length) {
      toast.success(
        uploaded.length === 1 ? t('files.uploadedOne', { name: uploaded[0] }) : t('files.uploadedMany', uploaded.length),
        t('nav.files')
      )
      await openFileBrowser(dirPath)
    }

    // Successful and conflicting rows are transient; only real failures stay up
    // until the user dismisses them or starts another upload, so an error in a
    // long list isn't missed.
    fileUploads.value = fileUploads.value.filter((entry) => entry.status === 'failed')
    return { uploaded, conflicts }
  }

  /**
   * Delete entries from the folder currently open in the browser.
   *
   * Resolves `{ deleted, errors, needsRecursive }` — `needsRecursive` holds the
   * non-empty folders the backend declined to remove, so the caller can confirm
   * once and call again with `recursive`.
   */
  async function deleteFileEntries(paths, { recursive = false } = {}) {
    const list = (Array.isArray(paths) ? paths : [paths]).filter(Boolean)
    if (!list.length) return { deleted: [], errors: [], needsRecursive: [] }

    let result
    try {
      result = await deleteServerFiles(currentServerId.value, list, { recursive })
    } catch (error) {
      const message = error?.message || t('files.deleteFailed')
      toast.error(message, t('nav.files'))
      return { deleted: [], errors: [{ error: message }], needsRecursive: [] }
    }

    const deleted = result.deleted || []
    const errors = result.errors || []
    const needsRecursive = errors.filter((entry) => entry.code === 'not-empty').map((entry) => entry.path)

    // A deleted file that is open in the editor would otherwise leave the page
    // guarding unsaved changes for something that no longer exists.
    if (fileEditor.value.path && deleted.some((path) => isPathInside(fileEditor.value.path, path))) {
      closeFile()
    }

    if (deleted.length) {
      toast.success(
        deleted.length === 1 ? t('files.deletedOne', { name: deleted[0] }) : t('files.deletedMany', deleted.length),
        t('nav.files')
      )
      await openFileBrowser(fileBrowser.value.currentPath || '')
    }

    for (const entry of errors) {
      if (entry.code === 'not-empty') continue
      toast.error(entry.path ? `${entry.path}: ${entry.error}` : entry.error, t('nav.files'))
    }

    return { deleted, errors, needsRecursive }
  }

  async function createFolder(name) {
    const dirPath = fileBrowser.value.currentPath || ''
    try {
      await createServerFolder(currentServerId.value, dirPath, name)
      toast.success(t('files.created', { name }), t('nav.files'))
      await openFileBrowser(dirPath)
      return true
    } catch (error) {
      toast.error(error?.message || t('files.createFolderFailed'), t('nav.files'))
      return false
    }
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
        error: error.message || t('files.search.failed'),
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
      toast.error(t('files.notEditable'), t('nav.files'))
      return
    }
    fileEditor.value = { path, content: '', originalContent: '', loading: true, saving: false, error: null }
    try {
      const file = await getServerFile(currentServerId.value, path)
      fileEditor.value = { path: file.path, content: file.content, originalContent: file.content, loading: false, saving: false, error: null }
    } catch (error) {
      const message = error?.message || t('files.openFailed')
      fileEditor.value = { path: null, content: '', originalContent: '', loading: false, saving: false, error: message }
      toast.error(message, t('nav.files'))
    }
  }

  async function saveFile() {
    if (!fileEditor.value.path || fileEditor.value.saving) return
    fileEditor.value.saving = true
    fileEditor.value.error = null
    try {
      await saveServerFile(currentServerId.value, fileEditor.value.path, fileEditor.value.content)
      fileEditor.value.originalContent = fileEditor.value.content
      toast.success(t('files.saved'), t('nav.files'))
    } catch (error) {
      const message = error?.message || t('files.saveFailed')
      fileEditor.value.error = message
      toast.error(message, t('nav.files'))
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
      toast.success(t('servers.deleted'), t('servers.title'))
      await loadServers()
      router.push({ name: 'Servers' })
    } catch (error) {
      console.error('Failed to delete server:', error)
      toast.error(error.message || t('servers.deleteFailed'), t('servers.errorTitle'))
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
      }
      await installMod(modData.modId, {
        mc_version: modData.mcVersion,
        loader: modData.loader,
        server_id: currentServerId.value
      })
      const message = prereqs.length > 0
        ? t('mods.installedWithDeps', { title: modData.modTitle }, prereqs.length)
        : t('mods.installedToast', { title: modData.modTitle })
      toast.success(message, t('mods.installedTitle'))
      await loadMods()
    } catch (error) {
      console.error('Install failed:', error)
      toast.error(error.message || t('mods.installFailed'), t('common.installationFailed'))
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
      toast.info(t('mods.noVersionList'), t('mods.noVersionListTitle'))
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
        t('mods.versionChanged', { title: target.title || t('content.mod', 1), version: versionNumber }),
        t('mods.versionChangedTitle')
      )
      await loadMods()
    } catch (error) {
      console.error('Version change failed:', error)
      toast.error(error.message || t('mods.versionChangeFailed'), t('mods.installFailedTitle'))
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

  // Returns true while the worker is still going, so the caller's poll knows
  // whether to schedule another tick.
  async function fetchServerInstallProgress() {
    if (!currentServerId.value) return false
    try {
      const progress = await getServerInstallProgress(currentServerId.value)
      serverInstallProgress.value = progress?.active ? progress : null
    } catch {
      // polling failure is non-critical — silently swallow
    }
    return serverInstallProgress.value !== null
  }

  function clearServerInstallProgress() {
    serverInstallProgress.value = null
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
      const summary = [
        t('modpacks.installedToast', { title: modpackData.title }),
        t('modpacks.notes.replaced', { n: cleanedCount }),
        missingCount ? t('modpacks.notes.missing', { n: missingCount }) : '',
        skippedCount ? t('modpacks.notes.skipped', skippedCount) : '',
        uncertainCount ? t('modpacks.notes.uncertain', uncertainCount) : '',
        result?.backup_file ? t('modpacks.notes.backup', { file: result.backup_file }) : ''
      ]
      toast.success(summary.filter(Boolean).join(' '), t('modpacks.installedTitle'))
      if (uncertainCount) {
        toast.warning(t('modpacks.unknownSideKept'), t('modpacks.compatibilityWarningTitle'))
      }
      if (result?.java_warning) toast.warning(result.java_warning.message, t('modpacks.javaMismatchTitle'))
      await Promise.all([loadServer({ silent: true }), loadMods()])
    } catch (error) {
      const uncertainMods = error?.data?.uncertain_mod_files
      const canContinueWithUncertain = Boolean(error?.data?.can_continue_with_uncertain)
      if (error?.status === 409 && canContinueWithUncertain && Array.isArray(uncertainMods) && uncertainMods.length) {
        showModpackInstallConfirmModal.value = false
        pendingUncertainModpackData.value = modpackData
        uncertainModsReport.value = uncertainMods
        showUncertainModsModal.value = true
        toast.warning(t('modpacks.needsSideDecision'), t('modpacks.uncertainSideTitle'))
        return
      }
      const missingFiles = error?.data?.missing_files
      const canContinue = Boolean(error?.data?.can_continue_with_missing)
      if (!modpackData.allowMissing && error?.status === 409 && canContinue && Array.isArray(missingFiles) && missingFiles.length) {
        showModpackInstallConfirmModal.value = false
        pendingMissingModsInstall.value = { ...modpackData, allowMissing: true }
        missingModsReport.value = missingFiles
        showMissingModsConfirmModal.value = true
        toast.warning(t('modpacks.missingFilesToast', missingFiles.length), t('modpacks.missingFilesTitle'))
        return
      }
      showModpackInstallConfirmModal.value = false
      console.error('Modpack install failed:', error)
      toast.error(error.message || t('modpacks.installFailed'), t('common.installationFailed'))
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
    toast.info(t('modpacks.installCanceled'), t('modpacks.installCanceledTitle'))
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
      title: t('mods.remove.title'),
      message: t('mods.remove.message', { name: mod.name }),
      description: t('mods.remove.description'),
      type: 'danger',
      confirmText: t('common.remove'),
      cancelText: t('common.cancel')
    }
    showConfirmModal.value = true
  }

  async function confirmRemoveMod() {
    if (!modToRemove.value) return
    if (modToRemove.value === '__bulk__') {
      await confirmBulkRemoveMods()
      return
    }
    if (modToRemove.value === '__update__') {
      await confirmUpdateAllMods()
      return
    }
    const filename = modToRemove.value.filename || modToRemove.value.name
    try {
      await removeMod(currentServerId.value, filename)
      // Drop cache entry so re-list doesn't show stale metadata if a
      // different jar with the same filename ever lands later.
      invalidateModrinthMetaCache(filename)
      toast.success(t('mods.remove.done', { name: modToRemove.value.name }), t('mods.remove.doneTitle'))
      await loadMods()
    } catch (error) {
      console.error('Failed to remove mod:', error)
      toast.error(t('mods.remove.failed'), t('common.error'))
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
      title: t('mods.bulkRemove.title'),
      message: t('mods.bulkRemove.message', n),
      description: t('mods.bulkRemove.description'),
      type: 'danger',
      confirmText: t('mods.bulkRemove.confirm', n),
      cancelText: t('common.cancel')
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
      toast.success(t('mods.bulkRemove.done', filenames.length), t('mods.bulkRemove.doneTitle'))
      await loadMods()
    } catch (error) {
      console.error('Failed to bulk remove mods:', error)
      toast.error(t('mods.bulkRemove.failed'), t('common.error'))
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

  async function setSelectedModsEnabled(enabled) {
    const filenames = selectedMods.value.filter((m) => m.disabled === enabled).map((m) => m.filename)
    if (!filenames.length || togglingMods.value) return
    togglingMods.value = true
    try {
      const { renamed, errors } = await setModsEnabled(currentServerId.value, filenames, enabled)
      const n = Object.keys(renamed || {}).length
      if (n) {
        const done = enabled ? t('mods.toggle.enabled', n) : t('mods.toggle.disabled', n)
        const restart = serverStatus.value.status === 'running' ? ` ${t('mods.toggle.restartToApply')}` : ''
        toast.success(`${done}${restart}`, enabled ? t('mods.toggle.enabledTitle') : t('mods.toggle.disabledTitle'))
      }
      if (errors?.length) {
        const title = enabled
          ? t('mods.toggle.notEnabled', { n: errors.length })
          : t('mods.toggle.notDisabled', { n: errors.length })
        toast.error(`${errors[0].filename}: ${errors[0].error}`, title)
      }
      await loadMods()
    } catch (error) {
      console.error('Failed to toggle mods:', error)
      toast.error(enabled ? t('mods.toggle.enableFailed') : t('mods.toggle.disableFailed'), t('common.error'))
    } finally {
      selectedModPaths.value = new Set()
      togglingMods.value = false
    }
  }

  async function performServerAction(action, fn, successMessage) {
    if (actionState.value[action]) return
    actionState.value[action] = true
    try {
      const result = await fn(currentServerId.value)
      if (result.success) {
        toast.success(successMessage, t('servers.updatedTitle'))
      } else {
        toast.error(result.message || t('common.operationFailed'), t('servers.errorTitle'))
      }
    } catch (error) {
      console.error(`Failed to ${action} server:`, error)
      if ((action === 'start' || action === 'restart') && (error.data?.java_missing || error.data?.java_too_old)) {
        pendingJavaAction.value = action
        showJavaModal.value = true
      } else {
        toast.error(error.message || t(`servers.actionFailed.${action}`), t('servers.errorTitle'))
      }
    } finally {
      actionState.value[action] = false
      await loadServer()
      if (action === 'start' || action === 'restart') {
        await loadLogs()
      }
    }
  }

  function handleStart() { return performServerAction('start', startServer, t('servers.startRequested')) }
  function handleStop()  { return performServerAction('stop',  stopServer,  t('servers.stopRequested')) }
  function handleRestart() { return performServerAction('restart', restartServer, t('servers.restartRequested')) }

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
      // A failed poll observes nothing about the install, which keeps running
      // in a backend worker regardless, so transient failures are ridden out
      // rather than reported as a failed install (see utils/pollProgress).
      const poll = createProgressPoller(() => getServerInstallProgress(installServerId))
      let progress = null
      let lostContact = false
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS))
        const result = await poll()
        if (result.status === 'retry') {
          console.warn(
            `Install-progress poll failed (attempt ${result.failures}); retrying`,
            result.error,
          )
          continue
        }
        if (result.status === 'giveup') {
          console.error('Install-progress poll gave up:', result.error)
          lostContact = true
          break
        }
        progress = result.progress
        if (!progress.active || progress.phase === 'done' || progress.phase === 'failed') break
      }
      if (lostContact) {
        // Deliberately a warning, not an error: we do not know that the install
        // failed, and it most likely did not.
        toast.warning(lostContactMessage(), t('install.title'))
      } else if (progress.phase === 'done') {
        toast.success(t('install.success'), t('install.title'))
      } else {
        toast.error(progress.error || t('install.failed'), t('install.title'))
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
        toast.error(error.message || t('install.serverFailed'), t('servers.errorTitle'))
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
      toast.success(t('console.commandSent'), t('nav.console'))
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
      toast.error(t('console.commandFailed'), t('console.errorTitle'))
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
      toast.success(t('properties.saved'), t('properties.savedTitle'))
    } catch (error) {
      console.error('Failed to save settings:', error)
      toast.error(error.message || t('properties.saveFailed'), t('common.error'))
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
      toast.success(t('settings.autostart.updated'), t('nav.settings'))
    } catch (error) {
      server.value = { ...server.value, autoStart: previous }  // rollback
      toast.error(error.message || t('settings.autostart.updateFailed'), t('common.error'))
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
    togglingMods.value = false
    modUpdates.value = {}
    modUpdateDeps.value = []
    updatingMods.value = false
    serverLoading.value = true
    modsLoading.value = false
    logsLoading.value = false
    installLoading.value = false
    modpackInstalling.value = false
    modpackProgress.value = null
    serverInstallProgress.value = null
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
    iconUrlFor,
    savedMotd,
    iconChanged,
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
    togglingMods,
    selectedEnabledCount,
    selectedDisabledCount,
    modUpdates,
    updatingMods,
    installLoading,
    modpackInstalling,
    actionState,
    consoleCommand,
    commandSending,
    commandHistory,
    fileBrowser,
    fileEditor,
    fileUploads,
    fileSearch,
    showDeleteServerModal,
    deletingServer,
    modpackProgress,
    serverInstallProgress,
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
    installActivity,
    installDisplay,
    serverInstalling,
    backgroundModpackInstalling,
    backgroundModpackLabel,
    backgroundModpackPercent,
    backgroundModpack,
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
    saveServerOrder,
    loadServer,
    loadMods,
    loadLogs,
    refreshAll,
    openFileBrowser,
    enterFileEntry,
    goUpDirectory,
    uploadFiles,
    cancelUpload,
    clearFinishedUploads,
    deleteFileEntries,
    createFolder,
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
    fetchServerInstallProgress,
    clearServerInstallProgress,
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
    setSelectedModsEnabled,
    updateAllMods,
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
