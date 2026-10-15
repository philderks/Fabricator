<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import FormField from '../../components/ui/FormField.vue'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import { useServerStore } from '../../stores/server'
import { useAuthStore } from '../../stores/auth'
import { deleteServerIcon, getInstalledJava, getJavaStatus, getLoaderGameVersions, getServerInstallProgress, setServerIcon, upgradeServer } from '../../api/servers'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

const store = useServerStore()
const auth = useAuthStore()
const toast = useToast()

// Server icon (#85). Saved immediately rather than with the form: it's a file,
// not a server.properties key. The img's own load/error says whether one exists.
const hasIcon = ref(false)
const iconBusy = ref(false)
const iconVersion = ref(Date.now())
const iconInput = ref(null)
const iconUrl = computed(() => `/api/servers/${store.currentServerId}/icon?v=${iconVersion.value}`)

async function changeIcon(action, successKey) {
  iconBusy.value = true
  try {
    await action()
    iconVersion.value = Date.now()
    const restart = store.canEditSettings ? '' : ` ${t('properties.icon.restartToShow')}`
    toast.success(`${t(successKey)}${restart}`, t('properties.icon.toastTitle'))
  } catch (error) {
    toast.error(error.message || t('properties.icon.updateFailed'), t('common.error'))
  } finally {
    iconBusy.value = false
  }
}

function onIconPicked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) changeIcon(() => setServerIcon(store.currentServerId, file), 'properties.icon.updated')
}

function removeIcon() {
  changeIcon(() => deleteServerIcon(store.currentServerId), 'properties.icon.removed')
}

// First-stage migrations are deliberately limited to jar-only server types.
// Fabric/Forge/NeoForge need per-mod compatibility resolution before they can
// be safely offered here.
const canUpgrade = computed(() => ['vanilla', 'paper'].includes(store.server?.loader))
const upgradeVersions = ref([])
const targetUpgradeVersion = ref('')
const upgradeStarting = ref(false)
const upgradePhase = ref('')

// Mirrors the backend's upgrade ordering: a numbered release in either naming
// scheme ('1.21.4' or the year-based '26.3') parses to a major/minor/patch
// triple, so the schemes order against each other for free — every 26.x
// release sorts above every 1.x one. Anything not a bare numeric release
// (snapshots, '-rc' builds) yields null and is never offered as a target.
function parseMinecraftRelease(version) {
  const match = /^(\d+)\.(\d+)(?:\.(\d+))?$/.exec(String(version ?? '').trim())
  if (!match) return null
  return [Number(match[1]), Number(match[2]), Number(match[3] ?? 0)]
}

function isNewerMinecraftRelease(candidate, current) {
  const a = parseMinecraftRelease(candidate)
  const b = parseMinecraftRelease(current)
  if (!a || !b) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i]
  }
  return false
}

async function loadUpgradeVersions() {
  if (!canUpgrade.value) return
  try {
    const versions = await getLoaderGameVersions(store.server.loader)
    const current = store.server.version
    // Filter on "is a numbered release" rather than the loader's `stable`
    // flag, so this list mirrors exactly what POST /upgrade accepts.
    // isNewerMinecraftRelease already rejects anything that is not a bare
    // numbered release, so snapshots and -rc/-pre builds stay out. The
    // `stable` flag is not usable here: PaperMC marks every year-based
    // family non-stable, which would leave a 26.x Paper server with an
    // empty target list even though the upgrade itself is supported.
    upgradeVersions.value = (versions || [])
      .filter((entry) => isNewerMinecraftRelease(entry.version, current))
      .map((entry) => entry.version)
    targetUpgradeVersion.value = upgradeVersions.value[0] || ''
  } catch {
    upgradeVersions.value = []
  }
}

async function startUpgrade() {
  const target = targetUpgradeVersion.value
  if (!target || !store.server?.id) return
  const confirmed = window.confirm(
    t('properties.upgrade.confirm', { name: store.server.name, from: store.server.version, to: target })
  )
  if (!confirmed) return
  upgradeStarting.value = true
  upgradePhase.value = 'starting'
  try {
    await upgradeServer(store.server.id, target)
    toast.info(t('properties.upgrade.started'))
    let progress
    do {
      progress = await getServerInstallProgress(store.server.id)
      upgradePhase.value = progress?.phase || 'working'
      if (progress?.active) await new Promise((resolve) => setTimeout(resolve, 1000))
    } while (progress?.active)

    if (progress?.phase === 'done') {
      await store.loadServer({ silent: true })
      toast.success(t('properties.upgrade.done', { version: target }))
    } else {
      toast.error(progress?.error || t('properties.upgrade.failed'))
    }
  } catch (error) {
    toast.error(error?.message || t('properties.upgrade.startFailed'))
  } finally {
    upgradeStarting.value = false
    upgradePhase.value = ''
  }
}

const isDirty = computed(() => store.isDirtySettings)

const showAdvanced = ref(false)

const motdCharacters = computed(() => store.serverSettings?.motd?.length ?? 0)
const statusIntervalDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableStatus
)
const queryDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableQuery
)
const rconDisabled = computed(
  () => !store.canEditSettings || !store.serverSettings?.enableRcon
)

// Per-server heap allocation unit (drives the JVM -Xms/-Xmx flags). The input's
// bounds/step follow the chosen unit, and switching units converts the current
// value so the real allocation is preserved (4 GB ⇄ 4096 MB), not turned into
// 4 MB. This is distinct from the Overview display preference in General
// Settings — this one changes what the server is actually launched with.
const memoryLimits = computed(() =>
  store.serverSettings?.memoryUnit === 'MB'
    ? { min: 512, max: 65536, step: 256 }
    : { min: 1, max: 64, step: 0.5 }
)

const onMemoryUnitChange = (nextUnit) => {
  const s = store.serverSettings
  if (!s || nextUnit === s.memoryUnit) return
  const convert = (value) => {
    const current = Number(value) || 0
    if (nextUnit === 'MB' && s.memoryUnit === 'GB') {
      return Math.round(current * 1024)
    } else if (nextUnit === 'GB' && s.memoryUnit === 'MB') {
      return Math.round((current / 1024) * 100) / 100
    }
    return current
  }

  s.memoryMin = convert(s.memoryMin ?? s.memory)
  s.memory = convert(s.memory)
  s.memoryUnit = nextUnit
}

// ─── Java runtime + launch flags (#54) ──────────────────────────────────────
// Both were already honoured per server by the launch builder but had no UI
// after creation, so the only way to pin a JVM was renaming managed JDK folders
// and hand-editing files in the server directory.

const installedJava = ref([])
const requiredJava = ref(null)
// Forces the custom-path row open while the field is still empty, which is
// otherwise indistinguishable from "Automatic".
const customJavaOpen = ref(false)
const customJavaProbe = ref(null)

const javaSelection = computed(() => {
  const path = store.serverSettings?.javaPath || ''
  if (!path) return customJavaOpen.value ? 'custom' : 'auto'
  const managed = installedJava.value.find((entry) => entry.path === path)
  return managed ? `managed:${managed.major}` : 'custom'
})

function onJavaSelectionChange(value) {
  const settings = store.serverSettings
  if (!settings) return
  customJavaProbe.value = null
  if (value === 'auto') {
    customJavaOpen.value = false
    settings.javaPath = ''
    return
  }
  if (value === 'custom') {
    customJavaOpen.value = true
    // Keep whatever is already there so switching away and back isn't
    // destructive; an unknown path already reads as 'custom'.
    return
  }
  const major = Number(value.slice('managed:'.length))
  const managed = installedJava.value.find((entry) => entry.major === major)
  if (managed) {
    customJavaOpen.value = false
    settings.javaPath = managed.path
  }
}

// The version a custom path actually reports — the whole point of the field is
// choosing a specific JVM, so guessing from the path would defeat it.
async function probeCustomJava() {
  const path = store.serverSettings?.javaPath?.trim()
  if (!path) {
    customJavaProbe.value = null
    return
  }
  try {
    const status = await getJavaStatus({
      javaPath: path,
      mcVersion: store.server?.version
    })
    customJavaProbe.value = {
      available: Boolean(status?.installed ?? status?.available),
      major: status?.detected_java ?? status?.major_version ?? null
    }
  } catch {
    customJavaProbe.value = null
  }
}

const selectedJavaMajor = computed(() => {
  if (javaSelection.value === 'auto') return null
  if (javaSelection.value === 'custom') return customJavaProbe.value?.major ?? null
  return Number(javaSelection.value.slice('managed:'.length))
})

const javaWarning = computed(() => {
  if (customJavaProbe.value && customJavaProbe.value.available === false) {
    return t('properties.java.cannotRun')
  }
  const required = requiredJava.value
  const selected = selectedJavaMajor.value
  if (!required || selected === null) return ''
  if (selected < required) {
    return t('properties.java.tooOld', { required, selected })
  }
  return ''
})

const javaAutoHint = computed(() =>
  requiredJava.value
    ? t('properties.java.autoHintVersion', { version: requiredJava.value })
    : t('properties.java.autoHint')
)

onMounted(async () => {
  if (auth.managed) return
  await loadUpgradeVersions()
  try {
    const payload = await getInstalledJava()
    installedJava.value = Array.isArray(payload?.managed) ? payload.managed : []
  } catch {
    installedJava.value = []
  }
  try {
    const status = await getJavaStatus({ mcVersion: store.server?.version })
    requiredJava.value = status?.required_java ?? null
  } catch {
    requiredJava.value = null
  }
})

// A saved or reset form replaces serverSettings wholesale; drop probe state so
// a stale "Detected Java 17" can't linger next to a different path.
watch(() => store.serverSettings, () => {
  customJavaProbe.value = null
  customJavaOpen.value = false
})

const modeLabel = computed(() => (showAdvanced.value ? t('properties.mode.expert') : t('properties.mode.basic')))
const modeDescription = computed(() =>
  showAdvanced.value
    ? t('properties.mode.expertDescription')
    : t('properties.mode.basicDescription')
)
const modeButtonLabel = computed(() =>
  showAdvanced.value ? t('properties.mode.switchToBasic') : t('properties.mode.enableExpert')
)

const toggleMode = () => {
  showAdvanced.value = !showAdvanced.value
}

const onSave = () => {
  if (!store.serverSettings || !store.canEditSettings) return
  store.handleSaveSettings(JSON.parse(JSON.stringify(store.serverSettings)))
}

const onReset = () => {
  if (!store.canEditSettings) return
  store.resetSettings()
}
</script>

<template>
  <div class="settings-page" v-if="store.serverSettings">
    <div class="settings-page__guard" v-if="!store.canEditSettings">
      {{ $t('properties.guard') }}
    </div>

    <Panel v-if="canUpgrade && !auth.managed" :title="$t('properties.upgrade.title')">
      <div class="settings-page__mode">
        <div>
          <p class="settings-page__mode-label">{{ $t('properties.upgrade.current', { version: store.server?.version }) }}</p>
          <p class="settings-page__mode-description">{{ $t('properties.upgrade.description') }}</p>
          <p v-if="upgradeStarting" class="settings-page__upgrade-progress">{{ $t('properties.upgrade.working', { phase: upgradePhase.replaceAll('_', ' ') }) }}</p>
        </div>
        <div class="settings-page__upgrade-actions">
          <select
            v-model="targetUpgradeVersion"
            class="settings-page__input"
            :disabled="upgradeStarting || !upgradeVersions.length"
            :aria-label="$t('properties.upgrade.targetLabel')"
          >
            <option v-for="version in upgradeVersions" :key="version" :value="version">{{ version }}</option>
          </select>
          <AppButton
            variant="warning"
            :loading="upgradeStarting"
            :disabled="!targetUpgradeVersion"
            @click="startUpgrade"
          >
            {{ $t('properties.upgrade.submit') }}
          </AppButton>
        </div>
      </div>
    </Panel>

    <Panel :title="$t('properties.mode.title')">
      <div class="settings-page__mode">
        <div>
          <p class="settings-page__mode-label">{{ modeLabel }}</p>
          <p class="settings-page__mode-description">{{ modeDescription }}</p>
        </div>
        <button
          type="button"
          class="settings-page__mode-button"
          :class="{ 'settings-page__mode-button--active': showAdvanced }"
          @click="toggleMode"
        >
          {{ modeButtonLabel }}
        </button>
      </div>
    </Panel>

    <Panel :title="$t('properties.identity.title')">
      <FormField class="settings-page__icon-field" :label="$t('properties.identity.icon')" :hint="$t('properties.identity.iconHint')">
        <template #default="{ id, describedBy }">
          <div class="settings-page__icon-row">
            <span class="settings-page__icon">
              <img v-show="hasIcon" :src="iconUrl" :alt="$t('properties.identity.iconAlt')" @load="hasIcon = true" @error="hasIcon = false" />
              <span v-if="!hasIcon" aria-hidden="true">?</span>
            </span>
            <input
              :id="id"
              ref="iconInput"
              type="file"
              accept="image/*"
              class="settings-page__icon-input"
              :aria-describedby="describedBy"
              @change="onIconPicked"
            />
            <AppButton variant="ghost" size="sm" :loading="iconBusy" @click="iconInput.click()">
              {{ hasIcon ? $t('properties.icon.change') : $t('properties.icon.upload') }}
            </AppButton>
            <AppButton v-if="hasIcon" variant="ghost" size="sm" :disabled="iconBusy" @click="removeIcon">{{ $t('common.remove') }}</AppButton>
          </div>
        </template>
      </FormField>
      <div class="settings-page__grid">
        <FormField :label="$t('properties.identity.name')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              :placeholder="$t('properties.identity.namePlaceholder')"
              v-model="store.serverSettings.name"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.identity.bugReportUrl')" :hint="$t('properties.identity.bugReportUrlHint')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="url"
              placeholder="https://example.com/issues"
              v-model="store.serverSettings.bugReportLink"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField :label="$t('properties.identity.motd')" :hint="$t('properties.identity.motdHint', { count: motdCharacters, max: 59 })">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              maxlength="59"
              :placeholder="$t('properties.identity.motdPlaceholder')"
              v-model="store.serverSettings.motd"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.identity.port')" :hint="$t('properties.identity.portHint')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="1024"
              max="65535"
              v-model.number="store.serverSettings.port"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField :label="$t('properties.identity.bindAddress')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="0.0.0.0"
              v-model="store.serverSettings.serverIp"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.identity.maxPlayers')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="1"
              max="1000"
              v-model.number="store.serverSettings.maxPlayers"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField :label="$t('properties.identity.runningVersion')" :hint="$t('properties.identity.runningVersionHint')">
          <template #default="{ id, describedBy }">
            <div class="settings-page__readonly">
              <input
                :id="id"
                class="settings-page__input"
                type="text"
                :value="store.serverStatus.version"
                readonly
                :aria-describedby="describedBy"
              />
              <span class="settings-page__readonly-badge">{{ $t('properties.readOnly') }}</span>
            </div>
          </template>
        </FormField>
        <FormField :label="$t('properties.identity.modLoader')" :hint="$t('properties.identity.modLoaderHint')">
          <template #default="{ id, describedBy }">
            <div class="settings-page__readonly">
              <input
                :id="id"
                class="settings-page__input"
                type="text"
                :value="store.serverStatus.loader"
                readonly
                :aria-describedby="describedBy"
              />
              <span class="settings-page__readonly-badge">{{ $t('properties.readOnly') }}</span>
            </div>
          </template>
        </FormField>
      </div>
    </Panel>

    <Panel :title="$t('properties.gameplay.title')">
      <div class="settings-page__grid">
        <FormField :label="$t('properties.gameplay.difficulty')">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.difficulty"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="peaceful">{{ $t('properties.gameplay.difficulties.peaceful') }}</option>
              <option value="easy">{{ $t('properties.gameplay.difficulties.easy') }}</option>
              <option value="normal">{{ $t('properties.gameplay.difficulties.normal') }}</option>
              <option value="hard">{{ $t('properties.gameplay.difficulties.hard') }}</option>
            </select>
          </template>
        </FormField>
        <FormField :label="$t('properties.gameplay.gamemode')">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.gamemode"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="survival">{{ $t('properties.gameplay.gamemodes.survival') }}</option>
              <option value="creative">{{ $t('properties.gameplay.gamemodes.creative') }}</option>
              <option value="adventure">{{ $t('properties.gameplay.gamemodes.adventure') }}</option>
              <option value="spectator">{{ $t('properties.gameplay.gamemodes.spectator') }}</option>
            </select>
          </template>
        </FormField>

        <FormField :label="$t('properties.gameplay.spawnProtection')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              max="128"
              v-model.number="store.serverSettings.spawnProtection"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.gameplay.idleTimeout')" :hint="$t('properties.gameplay.idleTimeoutHint')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              max="10080"
              v-model.number="store.serverSettings.playerIdleTimeout"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField :label="$t('properties.gameplay.pauseWhenEmpty')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="0"
                max="3600"
                v-model.number="store.serverSettings.pauseWhenEmptySeconds"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="$t('properties.gameplay.functionPermissionLevel')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1"
                max="4"
                v-model.number="store.serverSettings.functionPermissionLevel"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="$t('properties.gameplay.opPermissionLevel')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1"
                max="4"
                v-model.number="store.serverSettings.opPermissionLevel"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
        </template>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.forceGamemode"
          :label="$t('properties.gameplay.forceGamemode')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.hardcore"
          :label="$t('properties.gameplay.hardcore')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.allowFlight"
          :label="$t('properties.gameplay.allowFlight')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.pvp"
          :label="$t('properties.gameplay.pvp')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.whitelist"
          :label="$t('properties.gameplay.whitelist')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-if="showAdvanced"
          v-model="store.serverSettings.enforceWhitelist"
          :label="$t('properties.gameplay.enforceWhitelist')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.commandBlocks"
          :label="$t('properties.gameplay.commandBlocks')"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <Panel :title="$t('properties.world.title')">
      <div class="settings-page__notice settings-page__notice--warning">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
          <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div>
          <strong>{{ $t('properties.world.warningLabel') }}</strong>
          {{ $t('properties.world.warning') }}
        </div>
      </div>

      <div class="settings-page__grid">
        <FormField :label="$t('properties.world.levelName')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              v-model="store.serverSettings.levelName"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.world.levelType')">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              v-model="store.serverSettings.levelType"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            >
              <option value="default">{{ $t('properties.world.levelTypes.default') }}</option>
              <option value="flat">{{ $t('properties.world.levelTypes.flat') }}</option>
              <option value="large_biomes">{{ $t('properties.world.levelTypes.largeBiomes') }}</option>
              <option value="amplified">{{ $t('properties.world.levelTypes.amplified') }}</option>
            </select>
          </template>
        </FormField>

        <FormField :label="$t('properties.world.seed')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              :placeholder="$t('properties.world.seedPlaceholder')"
              v-model="store.serverSettings.seed"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField v-if="showAdvanced" :label="$t('properties.world.generatorSettings')">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="{}"
              v-model="store.serverSettings.generatorSettings"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField :label="$t('properties.world.maxWorldSize')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxWorldSize"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="$t('properties.world.entityBroadcastRange')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="10"
                max="500"
                v-model.number="store.serverSettings.entityBroadcastRangePercentage"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="$t('properties.world.maxChainedNeighborUpdates')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxChainedNeighborUpdates"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
        </template>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.generateStructures"
          :label="$t('properties.world.generateStructures')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnAnimals"
          :label="$t('properties.world.spawnAnimals')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnMonsters"
          :label="$t('properties.world.spawnMonsters')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.spawnNpcs"
          :label="$t('properties.world.spawnNpcs')"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <Panel v-if="showAdvanced" :title="$t('properties.resources.title')">
      <div class="settings-page__grid">
        <FormField :label="$t('properties.resources.url')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="url"
              placeholder="https://example.com/resource.zip"
              v-model="store.serverSettings.resourcePack"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.resources.sha1')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              :placeholder="$t('properties.resources.sha1Placeholder')"
              v-model="store.serverSettings.resourcePackSha1"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <FormField :label="$t('properties.resources.id')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              v-model="store.serverSettings.resourcePackId"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.resources.prompt')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              :placeholder="$t('properties.resources.promptPlaceholder')"
              v-model="store.serverSettings.resourcePackPrompt"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.requireResourcePack"
          :label="$t('properties.resources.require')"
          :disabled="!store.canEditSettings"
        />
      </div>

      <div class="settings-page__grid">
        <FormField :label="$t('properties.resources.enabledPacks')" :hint="$t('properties.resources.enabledPacksHint')">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="vanilla"
              v-model="store.serverSettings.initialEnabledPacks"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
        <FormField :label="$t('properties.resources.disabledPacks')">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              v-model="store.serverSettings.initialDisabledPacks"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" :title="$t('properties.network.title')">
      <div class="settings-page__grid settings-page__grid--three">
        <div class="settings-page__field">
          <span class="settings-page__label">{{ $t('properties.network.statusBroadcast') }}</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableStatus"
              :disabled="!store.canEditSettings"
            />
            <span>{{ $t('properties.network.enableStatus') }}</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="0"
            v-model.number="store.serverSettings.statusHeartbeatInterval"
            :disabled="statusIntervalDisabled"
          />
          <span class="settings-page__hint">{{ $t('properties.network.statusInterval') }}</span>
        </div>
        <FormField :label="$t('properties.network.rateLimit')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              v-model.number="store.serverSettings.rateLimit"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.network.compressionThreshold')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="-1"
              v-model.number="store.serverSettings.networkCompressionThreshold"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <div class="settings-page__field">
          <span class="settings-page__label">{{ $t('properties.network.queryPort') }}</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableQuery"
              :disabled="!store.canEditSettings"
            />
            <span>{{ $t('properties.network.enableQuery') }}</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="65535"
            v-model.number="store.serverSettings.queryPort"
            :disabled="queryDisabled"
          />
        </div>
        <div class="settings-page__field">
          <span class="settings-page__label">{{ $t('properties.network.rconPort') }}</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.enableRcon"
              :disabled="!store.canEditSettings"
            />
            <span>{{ $t('properties.network.enableRcon') }}</span>
          </label>
          <input
            class="settings-page__input"
            type="number"
            min="1"
            max="65535"
            v-model.number="store.serverSettings.rconPort"
            :disabled="rconDisabled"
          />
        </div>
        <FormField :label="$t('properties.network.rconPassword')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="password"
              v-model="store.serverSettings.rconPassword"
              :disabled="rconDisabled"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.onlineMode"
          :label="$t('properties.network.onlineMode')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.enforceSecureProfile"
          :label="$t('properties.network.enforceSecureProfile')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.hideOnlinePlayers"
          :label="$t('properties.network.hideOnlinePlayers')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.preventProxyConnections"
          :label="$t('properties.network.preventProxyConnections')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.logIps"
          :label="$t('properties.network.logIps')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.acceptsTransfers"
          :label="$t('properties.network.acceptsTransfers')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.useNativeTransport"
          :label="$t('properties.network.useNativeTransport')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.syncChunkWrites"
          :label="$t('properties.network.syncChunkWrites')"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <!-- Launch tuning. Hidden in managed mode, where the deployment owns the
         JVM and the settings API rejects both fields outright. -->
    <Panel v-if="!auth.managed" :title="$t('properties.java.title')">
      <div class="settings-page__notice settings-page__notice--info">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div>
          <strong>{{ $t('properties.headsUp') }}</strong> {{ $t('properties.java.notice') }}
        </div>
      </div>

      <div class="settings-page__grid">
        <FormField :label="$t('properties.java.title')" :hint="javaSelection === 'auto' ? javaAutoHint : ''">
          <template #default="{ id, describedBy }">
            <select
              :id="id"
              class="settings-page__select"
              :value="javaSelection"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
              @change="onJavaSelectionChange($event.target.value)"
            >
              <option value="auto">{{ $t('properties.java.auto') }}</option>
              <option
                v-for="entry in installedJava"
                :key="entry.path"
                :value="`managed:${entry.major}`"
              >
                {{ $t('properties.java.managedOption', { major: entry.major }) }}
              </option>
              <option value="custom">{{ $t('properties.java.customPath') }}</option>
            </select>
          </template>
        </FormField>

        <FormField
          v-if="javaSelection === 'custom'"
          :label="$t('properties.java.path')"
          :hint="customJavaProbe?.major ? $t('properties.java.detected', { major: customJavaProbe.major }) : $t('properties.java.pathHint')"
        >
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="text"
              placeholder="/usr/lib/jvm/java-25-openjdk/bin/java"
              v-model.trim="store.serverSettings.javaPath"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
              @blur="probeCustomJava"
            />
          </template>
        </FormField>
      </div>

      <div v-if="javaWarning" class="settings-page__notice settings-page__notice--warning" role="status">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 9V13M12 17H12.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <div>{{ javaWarning }}</div>
      </div>

      <FormField
        :label="$t('properties.java.jvmArgs')"
        :hint="$t('properties.java.jvmArgsHint')"
      >
        <template #default="{ id, describedBy }">
          <textarea
            :id="id"
            class="settings-page__input settings-page__textarea"
            rows="2"
            spellcheck="false"
            placeholder="-XX:+UseG1GC -XX:MaxGCPauseMillis=130"
            v-model.trim="store.serverSettings.jvmArgs"
            :disabled="!store.canEditSettings"
            :aria-describedby="describedBy"
          ></textarea>
        </template>
      </FormField>
    </Panel>

    <Panel :title="$t('properties.performance.title')">
      <div class="settings-page__notice settings-page__notice--info">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" />
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div>
          <strong>{{ $t('properties.headsUp') }}</strong> {{ $t('properties.performance.notice') }}
        </div>
      </div>

      <div class="settings-page__grid settings-page__grid--three">
        <FormField v-if="!auth.managed" :label="$t('properties.performance.memoryMin')" :hint="$t('properties.performance.memoryMinHint')">
          <template #default="{ id, describedBy }">
            <div class="settings-page__memory">
              <input
                :id="id"
                class="settings-page__input settings-page__memory-value"
                type="number"
                :min="memoryLimits.min"
                :max="store.serverSettings.memory"
                :step="memoryLimits.step"
                v-model.number="store.serverSettings.memoryMin"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
              <span class="settings-page__memory-unit">
                {{ store.serverSettings.memoryUnit }}
              </span>
            </div>
          </template>
        </FormField>
        <FormField v-if="!auth.managed" :label="$t('properties.performance.memoryMax')" :hint="$t('properties.performance.memoryMaxHint')">
          <template #default="{ id, describedBy }">
            <div class="settings-page__memory">
              <input
                :id="id"
                class="settings-page__input settings-page__memory-value"
                type="number"
                :min="store.serverSettings.memoryMin || memoryLimits.min"
                :max="memoryLimits.max"
                :step="memoryLimits.step"
                v-model.number="store.serverSettings.memory"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
              <select
                class="settings-page__select settings-page__memory-unit"
                :value="store.serverSettings.memoryUnit"
                :disabled="!store.canEditSettings"
                :aria-label="$t('properties.performance.memoryUnit')"
                @change="onMemoryUnitChange($event.target.value)"
              >
                <option value="GB">GB</option>
                <option value="MB">MB</option>
              </select>
            </div>
          </template>
        </FormField>
        <FormField :label="$t('properties.performance.viewDistance')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="3"
              max="32"
              v-model.number="store.serverSettings.viewDistance"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
        <FormField :label="$t('properties.performance.simulationDistance')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="3"
              max="32"
              v-model.number="store.serverSettings.simulationDistance"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>

        <template v-if="showAdvanced">
          <FormField :label="$t('properties.performance.maxTickTime')">
            <template #default="{ id, describedBy }">
              <input
                :id="id"
                class="settings-page__input"
                type="number"
                min="1000"
                v-model.number="store.serverSettings.maxTickTime"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              />
            </template>
          </FormField>
          <FormField :label="$t('properties.performance.regionFileCompression')">
            <template #default="{ id, describedBy }">
              <select
                :id="id"
                class="settings-page__select"
                v-model="store.serverSettings.regionFileCompression"
                :disabled="!store.canEditSettings"
                :aria-describedby="describedBy"
              >
                <option value="deflate">Deflate</option>
                <option value="gzip">Gzip</option>
                <option value="lz4">LZ4</option>
                <option value="zstd">Zstd</option>
              </select>
            </template>
          </FormField>
        </template>
      </div>
    </Panel>

    <Panel v-if="showAdvanced" :title="$t('properties.security.title')">
      <div class="settings-page__grid">
        <div class="settings-page__field">
          <span class="settings-page__label">{{ $t('properties.security.broadcastConsole') }}</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.broadcastConsoleToOps"
              :disabled="!store.canEditSettings"
            />
            <span>{{ $t('properties.enabled') }}</span>
          </label>
        </div>
        <div class="settings-page__field">
          <span class="settings-page__label">{{ $t('properties.security.broadcastRcon') }}</span>
          <label
            class="settings-page__toggle settings-page__toggle--inline"
            :class="{ 'settings-page__toggle--disabled': !store.canEditSettings }"
          >
            <input
              type="checkbox"
              v-model="store.serverSettings.broadcastRconToOps"
              :disabled="!store.canEditSettings"
            />
            <span>{{ $t('properties.enabled') }}</span>
          </label>
        </div>

        <FormField :label="$t('properties.security.textFilteringConfig')">
          <template #default="{ id, describedBy }">
            <textarea
              :id="id"
              class="settings-page__input settings-page__textarea"
              placeholder="{}"
              v-model="store.serverSettings.textFilteringConfig"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            ></textarea>
          </template>
        </FormField>
        <FormField :label="$t('properties.security.textFilteringVersion')">
          <template #default="{ id, describedBy }">
            <input
              :id="id"
              class="settings-page__input"
              type="number"
              min="0"
              v-model.number="store.serverSettings.textFilteringVersion"
              :disabled="!store.canEditSettings"
              :aria-describedby="describedBy"
            />
          </template>
        </FormField>
      </div>

      <div class="settings-page__toggles">
        <ToggleRow
          v-model="store.serverSettings.enableCodeOfConduct"
          :label="$t('properties.security.codeOfConduct')"
          :disabled="!store.canEditSettings"
        />
        <ToggleRow
          v-model="store.serverSettings.enableJmxMonitoring"
          :label="$t('properties.security.jmxMonitoring')"
          :disabled="!store.canEditSettings"
        />
      </div>
    </Panel>

    <Panel v-if="!auth.managed" :title="$t('properties.danger.title')">
      <div class="settings-page__danger">
        <p class="settings-page__danger-text">{{ $t('properties.danger.text') }}</p>
        <AppButton variant="danger" :loading="store.deletingServer" @click="store.openDeleteServerModal">
          {{ store.deletingServer ? $t('common.deletingEllipsis') : $t('properties.danger.deleteServer') }}
        </AppButton>
      </div>
    </Panel>

    <footer class="settings-page__footer" :aria-label="$t('properties.footerLabel')">
      <div class="settings-page__footer-inner">
        <AppButton
          variant="ghost"
          :disabled="!isDirty || !store.canEditSettings"
          @click="onReset"
        >
          {{ $t('properties.reset') }}
        </AppButton>
        <AppButton
          variant="primary"
          :disabled="!isDirty || !store.canEditSettings"
          @click="onSave"
        >
          {{ $t('properties.saveChanges') }}
        </AppButton>
      </div>
    </footer>
  </div>
  <div v-else class="settings-page__loading">{{ $t('properties.loading') }}</div>
</template>

<style scoped>
.settings-page {
  /* One definition for the reading column, so the fixed action bar below can
     line its buttons up with it instead of drifting off on a wide display.
     Inherited rather than laid out, so `position: fixed` doesn't break it. */
  --settings-column: 880px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: var(--settings-column);
  /* Centers the column instead of leaving it flush against the sidebar with a
     growing dead zone on wide/ultrawide monitors. The fixed footer below
     mirrors this with the same margin so its buttons stay under the column. */
  margin: 0 auto;
  padding-bottom: 80px;
}

.settings-page__loading {
  color: var(--text-muted);
  font-size: var(--text-sm);
  padding: var(--space-5);
  text-align: center;
}

.settings-page__guard {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  color: var(--warning);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  font-size: var(--text-sm);
}

.settings-page__mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.settings-page__mode-label {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.settings-page__mode-description {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__mode-button {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 12px;
  font-size: var(--text-sm);
  font-family: inherit;
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease;
}

.settings-page__mode-button:hover {
  border-color: var(--primary);
  color: var(--text-primary);
}

.settings-page__mode-button--active {
  border-color: var(--primary);
  color: var(--primary);
}

/* Panel renders its body as a plain block and global.css zeroes every margin,
   so stacked blocks inside one panel had nothing between them. It only looked
   broken in places because two rules below were patching it by hand — a
   margin-bottom on notices, a margin-top on toggle groups — which covered the
   adjacencies those happened to sit in and missed the rest. In Java Runtime
   that left the runtime/path grid flush against the JVM Arguments label
   whenever no warning was showing. One gap here replaces both patches and
   spaces every panel on the page the same way. */
.settings-page :deep(.panel__body) {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.settings-page__upgrade-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 210px;
}

.settings-page__upgrade-progress {
  color: var(--text-muted);
  font-size: var(--text-xs);
  margin: var(--space-2) 0 0;
  text-transform: capitalize;
}

.settings-page__upgrade-actions .settings-page__input {
  width: auto;
  min-width: 104px;
}

.settings-page__icon-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.settings-page__icon-field {
  margin-bottom: var(--space-4);
}

/* 64px, the size Minecraft renders it at, with pixelated scaling so what you
   see here is what players see. */
.settings-page__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-disabled);
  overflow: hidden;
}

.settings-page__icon img {
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.settings-page__icon-input {
  display: none;
}

.settings-page__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}

.settings-page__grid--three {
  grid-template-columns: repeat(3, 1fr);
}

.settings-page__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.settings-page__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.settings-page__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__input,
.settings-page__select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 10px;
  font-family: inherit;
  font-size: var(--text-sm);
  width: 100%;
}

.settings-page__memory {
  display: flex;
  gap: var(--space-2);
}

.settings-page__memory-value {
  flex: 1;
  min-width: 0;
}

.settings-page__memory-unit {
  width: auto;
  flex: 0 0 auto;
}

.settings-page__textarea {
  min-height: 72px;
  resize: vertical;
  font-family: var(--font-mono, ui-monospace, monospace);
}

.settings-page__input:focus,
.settings-page__select:focus {
  outline: none;
  border-color: var(--primary);
}

.settings-page__input:disabled,
.settings-page__select:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.settings-page__readonly {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.settings-page__readonly-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  white-space: nowrap;
}

/* Spacing above comes from the panel body's gap now, not a margin here. */
.settings-page__toggles {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.settings-page__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.settings-page__toggle--inline {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.settings-page__toggle input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--primary);
  cursor: pointer;
}

.settings-page__toggle--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settings-page__toggle--disabled input[type="checkbox"] {
  cursor: not-allowed;
}

.settings-page__notice {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.settings-page__notice strong {
  font-weight: 600;
}

.settings-page__notice--warning {
  border: 1px solid var(--warning);
  color: var(--warning);
  background: color-mix(in oklch, var(--warning) 10%, transparent);
}

.settings-page__notice--info {
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.settings-page__footer {
  position: fixed;
  bottom: 0;
  left: var(--sidebar-width);
  right: 0;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-color);
  box-shadow: var(--shadow-up);
  /* Same gutter the routed content uses, so the inner column below starts on
     exactly the same line as the panels above it — including on mobile, where
     that token tightens. */
  padding: var(--space-4) var(--app-content-padding);
  z-index: 10;
}

/* The bar stays full-bleed — it is what separates the actions from the page —
   but its buttons are capped to the content column, so Save lands just under
   the last panel rather than at the far edge of an ultrawide screen. */
.settings-page__footer-inner {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  max-width: var(--settings-column);
  margin: 0 auto;
}

.settings-page__danger {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.settings-page__danger-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

/* The footer needs no `left` override: --sidebar-width resolves to 0 below the
   breakpoint (global.css), so it already spans the full width once the sidebar
   becomes a drawer. Only the field grids and the footer's own padding change. */
@media (max-width: 768px) {
  .settings-page__grid,
  .settings-page__grid--three {
    grid-template-columns: 1fr;
  }

  .settings-page__footer {
    padding: var(--space-3);
  }

  /* Stretch the save/reset pair across the bar — at this width there is no
     reason to leave them huddled in a corner, and they become easy targets. */
  .settings-page__footer-inner > * {
    flex: 1;
  }
}
</style>
