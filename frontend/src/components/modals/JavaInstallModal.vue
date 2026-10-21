<template>
  <BaseModal
    :show="show"
    :title="modalTitle"
    size="small"
    @close="handleClose"
  >
    <div class="java-content">
      <!-- checking -->
      <template v-if="state === 'checking'">
        <div class="java-spinner"></div>
        <p class="java-heading">{{ $t('javaInstall.checking') }}</p>
        <p class="java-subtext">{{ $t('javaInstall.checkingHint') }}</p>
      </template>

      <!-- needs_java -->
      <template v-else-if="state === 'needs_java'">
        <div class="java-icon">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
            <path d="M12 10V14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <circle cx="12" cy="17.5" r="0.75" fill="currentColor"/>
          </svg>
        </div>
        <p class="java-heading">{{ $t('javaInstall.required', { major: requiredJava }) }}</p>
        <i18n-t :keypath="mcVersion ? 'javaInstall.requiresMc' : 'javaInstall.requires'" tag="p" class="java-subtext">
          <template #version><strong>{{ mcVersion }}</strong></template>
          <template #java><strong>{{ $t('java.version', { major: requiredJava }) }}</strong></template>
        </i18n-t>

        <div v-if="substitutionNotice" class="java-notice">
          {{ substitutionNotice }}
        </div>

        <div class="java-platform">
          <span class="platform-label">{{ $t('javaInstall.detected') }}</span>
          <span class="platform-value">{{ detectedJavaLabel }}</span>
        </div>

        <div v-if="asset" class="java-platform">
          <span class="platform-label">{{ $t('javaInstall.download') }}</span>
          <span class="platform-value" :title="asset.filename">{{ assetFilename }} ({{ formatMb(asset.size_bytes) }})</span>
        </div>

        <div v-if="assetError" class="java-error">
          {{ $t('javaInstall.assetError', { error: assetError }) }}
        </div>
      </template>

      <!-- downloading -->
      <template v-else-if="state === 'downloading'">
        <div class="java-icon primary">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <path d="M12 3v12M12 15l-4-4M12 15l4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M3 20h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="java-heading">{{ $t('javaInstall.downloading', { major: effectiveMajor }) }}</p>
        <p class="java-subtext">{{ $t('javaInstall.progress', { done: downloadedLabel, total: totalLabel, pct: progressPercent }) }}</p>
        <div class="install-progress">
          <div class="install-progress__track">
            <div class="install-progress__fill" :style="{ width: progressPercent + '%' }"></div>
          </div>
        </div>
      </template>

      <!-- confirming_install -->
      <template v-else-if="state === 'confirming_install'">
        <div class="java-icon success">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <path d="M5 12l5 5L20 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <p class="java-heading">{{ $t('javaInstall.downloadComplete') }}</p>
        <i18n-t keypath="javaInstall.readyToInstall" tag="p" class="java-subtext">
          <template #major>{{ effectiveMajor }}</template>
          <template #install><strong>{{ $t('common.install') }}</strong></template>
        </i18n-t>
      </template>

      <!-- installing -->
      <template v-else-if="state === 'installing'">
        <div class="java-spinner"></div>
        <p class="java-heading">{{ $t('javaInstall.installing', { major: effectiveMajor }) }}</p>
        <p class="java-subtext">{{ $t('javaInstall.installingHint') }}</p>
      </template>

      <!-- done -->
      <template v-else-if="state === 'done'">
        <div class="java-icon success">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M7 12.5l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <p class="java-heading">{{ $t('javaInstall.installed', { major: effectiveMajor }) }}</p>
        <p class="java-subtext">{{ $t('javaInstall.installedHint') }}</p>
        <div v-if="javaPath" class="java-platform">
          <span class="platform-label">{{ $t('javaInstall.installedAt') }}</span>
          <span class="platform-value" :title="javaPath">{{ javaPath }}</span>
        </div>
      </template>

      <!-- error -->
      <template v-else-if="state === 'error'">
        <div class="java-icon error">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M12 7v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <circle cx="12" cy="16.5" r="0.75" fill="currentColor"/>
          </svg>
        </div>
        <p class="java-heading">{{ $t('javaInstall.somethingWrong') }}</p>
        <p class="java-subtext java-error-message">{{ errorMessage }}</p>
      </template>
    </div>

    <template #footer>
      <template v-if="state === 'checking'">
        <AppButton variant="ghost" size="md" @click="handleClose">{{ $t('common.cancel') }}</AppButton>
      </template>

      <template v-else-if="state === 'needs_java'">
        <AppButton variant="ghost" size="md" @click="handleClose">{{ $t('common.cancel') }}</AppButton>
        <AppButton
          variant="primary"
          size="md"
          :disabled="!canDownload"
          @click="startDownload"
        >{{ $t('javaInstall.downloadButton', { major: effectiveMajor }) }}</AppButton>
      </template>

      <template v-else-if="state === 'downloading' || state === 'installing'">
        <AppButton variant="ghost" size="md" :loading="true">{{ $t('common.working') }}</AppButton>
      </template>

      <template v-else-if="state === 'confirming_install'">
        <AppButton variant="ghost" size="md" @click="handleClose">{{ $t('common.cancel') }}</AppButton>
        <AppButton variant="primary" size="md" @click="confirmInstall">{{ $t('common.install') }}</AppButton>
      </template>

      <template v-else-if="state === 'done'">
        <AppButton variant="ghost" size="md" @click="handleClose">{{ $t('common.close') }}</AppButton>
        <AppButton variant="primary" size="md" @click="finishAndStart">{{ $t('javaInstall.startServer') }}</AppButton>
      </template>

      <template v-else-if="state === 'error'">
        <AppButton variant="ghost" size="md" @click="handleClose">{{ $t('common.close') }}</AppButton>
        <AppButton variant="primary" size="md" @click="resetToNeedsJava">{{ $t('javaInstall.tryAgain') }}</AppButton>
      </template>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { getJavaStatus, installJava, getJavaInstallProgress } from '../../api/servers'
import { t } from '../../i18n'

const props = defineProps({
  show: { type: Boolean, required: true },
  mcVersion: { type: String, default: '' },
  // Legacy Forge also has a max Java, so the status check needs the loader.
  loader: { type: String, default: '' }
})

const emit = defineEmits(['close', 'java-installed'])

const state = ref('checking')
const statusPayload = ref(null)
const asset = ref(null)
const assetError = ref(null)
const requiredJava = ref(null)
const installMajor = ref(null)
const substituted = ref(false)
const systemJava = ref(null)
const managedJava = ref(null)

const taskId = ref(null)
const downloaded = ref(0)
const total = ref(0)
const javaPath = ref('')
const errorMessage = ref('')

let pollHandle = null

const effectiveMajor = computed(() => installMajor.value || requiredJava.value || '')
const canDownload = computed(() => !!requiredJava.value && !assetError.value)

const assetFilename = computed(() => {
  if (!asset.value?.filename) return ''
  const name = asset.value.filename
  return name.length > 44 ? name.slice(0, 41) + '...' : name
})

const progressPercent = computed(() => {
  if (!total.value) return 0
  const pct = Math.round((downloaded.value / total.value) * 100)
  return Math.max(0, Math.min(100, pct))
})

const formatMb = (bytes) => {
  if (!bytes) return '?'
  const mb = bytes / (1024 * 1024)
  return mb >= 100 ? `${Math.round(mb)} MB` : `${mb.toFixed(1)} MB`
}

const downloadedLabel = computed(() => formatMb(downloaded.value))
const totalLabel = computed(() => formatMb(total.value))

const detectedJavaLabel = computed(() => {
  if (!systemJava.value) return t('javaInstall.none')
  if (systemJava.value.version == null) return t('javaInstall.notInstalled')
  return t('java.version', { major: systemJava.value.version })
})

const substitutionNotice = computed(() => {
  if (!substituted.value) return ''
  return t('javaInstall.substituted', { required: requiredJava.value, major: installMajor.value })
})

const modalTitle = computed(() => {
  switch (state.value) {
    case 'downloading': return t('javaInstall.titles.downloading')
    case 'installing': return t('javaInstall.titles.installing')
    case 'confirming_install': return t('javaInstall.titles.confirming')
    case 'done': return t('javaInstall.titles.done')
    case 'error': return t('javaInstall.titles.error')
    default: return t('javaInstall.titles.default')
  }
})

const clearPoll = () => {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
}

const resetModalState = () => {
  clearPoll()
  state.value = 'checking'
  statusPayload.value = null
  asset.value = null
  assetError.value = null
  requiredJava.value = null
  installMajor.value = null
  substituted.value = false
  systemJava.value = null
  managedJava.value = null
  taskId.value = null
  downloaded.value = 0
  total.value = 0
  javaPath.value = ''
  errorMessage.value = ''
}

const applyStatus = (payload) => {
  statusPayload.value = payload
  requiredJava.value = payload?.required_java ?? null
  installMajor.value = payload?.install_major ?? payload?.required_java ?? null
  systemJava.value = payload?.system_java || null
  managedJava.value = payload?.managed_java || null
  asset.value = payload?.asset || null
  assetError.value = payload?.asset_error || null
  substituted.value = !!(payload?.asset?.substituted || payload?.managed_java?.substituted)
}

const hasCompatibleJava = (payload) => {
  if (payload?.system_java?.meets_requirement) return true
  if (payload?.managed_java?.installed) return true
  return false
}

const loadStatus = async () => {
  try {
    resetModalState()
    state.value = 'checking'
    const status = await getJavaStatus({ mcVersion: props.mcVersion, loader: props.loader })
    applyStatus(status)
    if (!requiredJava.value) {
      errorMessage.value = t('javaInstall.unknownRequirement')
      state.value = 'error'
      return
    }
    if (hasCompatibleJava(status)) {
      javaPath.value = status?.managed_java?.path || status?.system_java?.path || 'java'
      state.value = 'done'
      return
    }
    state.value = 'needs_java'
  } catch (err) {
    errorMessage.value = err?.message || t('javaInstall.checkFailed')
    state.value = 'error'
  }
}

const startDownload = async () => {
  clearPoll()
  downloaded.value = 0
  total.value = asset.value?.size_bytes || 0
  state.value = 'downloading'
  try {
    const res = await installJava(requiredJava.value)
    taskId.value = res.task_id
    if (res.install_major) installMajor.value = res.install_major
    if (res.substituted) substituted.value = true
    pollHandle = setInterval(pollProgress, 750)
  } catch (err) {
    errorMessage.value = err?.message || t('java.startFailed')
    state.value = 'error'
  }
}

const pollProgress = async () => {
  if (!taskId.value) return
  // Capture the active taskId before the await so we can detect a reset /
  // re-open mid-flight (state race) and bail without trampling fresh state.
  const localTaskId = taskId.value
  try {
    const task = await getJavaInstallProgress(localTaskId)
    if (taskId.value !== localTaskId) return
    downloaded.value = task.downloaded || 0
    total.value = task.total || total.value
    if (task.status === 'error') {
      clearPoll()
      errorMessage.value = task.error || t('javaInstall.taskFailed')
      state.value = 'error'
      return
    }
    if (task.status === 'installing' && state.value === 'downloading') {
      clearPoll()
      state.value = 'confirming_install'
      return
    }
    if (task.status === 'done') {
      clearPoll()
      javaPath.value = task.java_path || ''
      // `error` is terminal; every other state (downloading,
      // confirming_install, installing, and the rare done re-poll) transitions
      // forward to `done`.
      if (state.value === 'error') return
      state.value = 'done'
    }
  } catch (err) {
    if (taskId.value !== localTaskId) return
    clearPoll()
    errorMessage.value = err?.message || t('java.lostContact')
    state.value = 'error'
  }
}

const confirmInstall = () => {
  state.value = 'installing'
  // The backend thread is already extracting; resume polling for completion.
  clearPoll()
  pollHandle = setInterval(pollProgress, 500)
}

const finishAndStart = () => {
  emit('java-installed')
  emit('close')
}

const resetToNeedsJava = () => {
  errorMessage.value = ''
  loadStatus()
}

const handleClose = () => {
  clearPoll()
  emit('close')
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      loadStatus()
    } else {
      clearPoll()
    }
  }
)

// Refresh status when the target Minecraft version changes mid-modal — the
// required-Java major may shift. Skips initial fire (no `immediate: true`)
// to avoid double-trigger with the `show` watcher above.
watch(
  () => props.mcVersion,
  () => {
    if (!props.show) return
    clearPoll()
    loadStatus()
  }
)

onBeforeUnmount(clearPoll)
</script>

<style scoped>
.java-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  text-align: center;
}

.java-icon {
  width: 52px;
  height: 52px;
  color: var(--warning);
  display: flex;
  align-items: center;
  justify-content: center;
}

.java-icon.success {
  color: var(--success);
}

.java-icon.primary {
  color: var(--primary);
}

.java-icon.error {
  color: var(--danger);
}

.java-heading {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  line-height: var(--leading-tight);
}

.java-subtext {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-normal);
  max-width: 36em;
}

.java-error-message {
  color: var(--danger);
  word-break: break-word;
}

.java-platform {
  display: flex;
  justify-content: space-between;
  width: 100%;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.platform-label {
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.platform-value {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.java-notice {
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  width: 100%;
  text-align: left;
}

.java-error {
  font-size: var(--text-xs);
  color: var(--danger);
  background: color-mix(in oklch, var(--danger) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--danger) 28%, transparent);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  width: 100%;
  text-align: left;
}

.java-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: java-modal-spin 0.8s linear infinite;
}

@keyframes java-modal-spin {
  to { transform: rotate(360deg); }
}

.install-progress {
  width: 100%;
  margin-top: var(--space-2);
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
</style>
