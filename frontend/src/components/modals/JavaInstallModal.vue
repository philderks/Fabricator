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
        <p class="java-heading">Checking Java...</p>
        <p class="java-subtext">Looking for a compatible Java runtime.</p>
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
        <p class="java-heading">Java {{ requiredJava }} is required</p>
        <p class="java-subtext">
          <template v-if="mcVersion">
            Minecraft <strong>{{ mcVersion }}</strong> requires <strong>Java {{ requiredJava }}</strong>.
          </template>
          <template v-else>
            This server requires <strong>Java {{ requiredJava }}</strong>.
          </template>
          Fabricator can download and install it automatically.
        </p>

        <div v-if="substitutionNotice" class="java-notice">
          {{ substitutionNotice }}
        </div>

        <div class="java-platform">
          <span class="platform-label">Detected Java:</span>
          <span class="platform-value">{{ detectedJavaLabel }}</span>
        </div>

        <div v-if="asset" class="java-platform">
          <span class="platform-label">Download:</span>
          <span class="platform-value" :title="asset.filename">{{ assetFilename }} ({{ formatMb(asset.size_bytes) }})</span>
        </div>

        <div v-if="assetError" class="java-error">
          Could not look up download asset: {{ assetError }}
        </div>
      </template>

      <!-- downloading -->
      <template v-else-if="state === 'downloading'">
        <div class="java-icon">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <path d="M12 3v12M12 15l-4-4M12 15l4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M3 20h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <p class="java-heading">Downloading Java {{ effectiveMajor }}</p>
        <p class="java-subtext">{{ downloadedLabel }} of {{ totalLabel }} ({{ progressPercent }}%)</p>
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
        <p class="java-heading">Download complete</p>
        <p class="java-subtext">
          Java {{ effectiveMajor }} is ready to install. Click <strong>Install</strong> to extract it to Fabricator's managed location.
        </p>
      </template>

      <!-- installing -->
      <template v-else-if="state === 'installing'">
        <div class="java-spinner"></div>
        <p class="java-heading">Installing Java {{ effectiveMajor }}...</p>
        <p class="java-subtext">Extracting and finalising the runtime. This only takes a few seconds.</p>
      </template>

      <!-- done -->
      <template v-else-if="state === 'done'">
        <div class="java-icon success">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M7 12.5l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <p class="java-heading">Java {{ effectiveMajor }} installed</p>
        <p class="java-subtext">
          The managed Java runtime is ready. You can start your server now.
        </p>
        <div v-if="javaPath" class="java-platform">
          <span class="platform-label">Installed at:</span>
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
        <p class="java-heading">Something went wrong</p>
        <p class="java-subtext java-error-message">{{ errorMessage }}</p>
      </template>
    </div>

    <template #footer>
      <template v-if="state === 'checking'">
        <button class="btn btn-secondary" @click="handleClose">Cancel</button>
      </template>

      <template v-else-if="state === 'needs_java'">
        <button class="btn btn-secondary" @click="handleClose">Cancel</button>
        <button
          class="btn btn-primary"
          :disabled="!canDownload"
          @click="startDownload"
        >
          Download Java {{ effectiveMajor }}
        </button>
      </template>

      <template v-else-if="state === 'downloading' || state === 'installing'">
        <button class="btn btn-secondary" disabled>Working...</button>
      </template>

      <template v-else-if="state === 'confirming_install'">
        <button class="btn btn-secondary" @click="handleClose">Cancel</button>
        <button class="btn btn-primary" @click="confirmInstall">Install</button>
      </template>

      <template v-else-if="state === 'done'">
        <button class="btn btn-secondary" @click="handleClose">Close</button>
        <button class="btn btn-primary" @click="finishAndStart">Start Server</button>
      </template>

      <template v-else-if="state === 'error'">
        <button class="btn btn-secondary" @click="handleClose">Close</button>
        <button class="btn btn-primary" @click="resetToNeedsJava">Try Again</button>
      </template>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import BaseModal from './BaseModal.vue'
import { getJavaStatus, installJava, getJavaInstallProgress } from '../../api/servers'

const props = defineProps({
  show: { type: Boolean, required: true },
  mcVersion: { type: String, default: '' }
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
  if (!systemJava.value) return 'None'
  if (systemJava.value.version == null) return 'Not installed'
  return `Java ${systemJava.value.version}`
})

const substitutionNotice = computed(() => {
  if (!substituted.value) return ''
  return `Java ${requiredJava.value} is not distributed by Adoptium; installing Java ${installMajor.value} instead (fully compatible).`
})

const modalTitle = computed(() => {
  switch (state.value) {
    case 'downloading': return 'Downloading Java'
    case 'installing': return 'Installing Java'
    case 'confirming_install': return 'Ready to install'
    case 'done': return 'Java installed'
    case 'error': return 'Java install failed'
    default: return 'Java Required'
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
    const status = await getJavaStatus({ mcVersion: props.mcVersion })
    applyStatus(status)
    if (!requiredJava.value) {
      errorMessage.value = 'Could not determine the Java version this server needs.'
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
    errorMessage.value = err?.message || 'Failed to check Java status.'
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
    errorMessage.value = err?.message || 'Failed to start Java install.'
    state.value = 'error'
  }
}

const pollProgress = async () => {
  if (!taskId.value) return
  try {
    const task = await getJavaInstallProgress(taskId.value)
    downloaded.value = task.downloaded || 0
    total.value = task.total || total.value
    if (task.status === 'error') {
      clearPoll()
      errorMessage.value = task.error || 'The install task failed.'
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
      if (state.value === 'downloading' || state.value === 'confirming_install') {
        // Edge case: install finished before user confirmed. Treat confirm as
        // already-accepted and jump to done.
        state.value = 'done'
      } else if (state.value === 'installing') {
        state.value = 'done'
      }
    }
  } catch (err) {
    clearPoll()
    errorMessage.value = err?.message || 'Lost contact with the install task.'
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

onBeforeUnmount(clearPoll)
</script>

<style scoped>
.java-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
  padding: 8px 0;
}

.java-icon {
  color: var(--warning, #f59e0b);
  display: flex;
  align-items: center;
  justify-content: center;
}

.java-icon.success {
  color: var(--primary, #22c55e);
}

.java-icon.error {
  color: var(--danger, #ef4444);
}

.java-heading {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.java-subtext {
  font-size: 0.9375rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.java-error-message {
  color: var(--danger, #ef4444);
  word-break: break-word;
}

.java-platform {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 0.875rem;
  width: 100%;
  justify-content: center;
}

.platform-label {
  color: var(--text-secondary);
}

.platform-value {
  color: var(--text-primary);
  font-weight: 500;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.java-notice {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  width: 100%;
  line-height: 1.5;
}

.java-error {
  font-size: 0.8125rem;
  color: var(--danger, #ef4444);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  width: 100%;
  line-height: 1.5;
}

.java-spinner {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary, #22c55e);
  animation: java-spin 0.8s linear infinite;
}

@keyframes java-spin {
  to { transform: rotate(360deg); }
}

.install-progress {
  margin-top: 4px;
  width: 100%;
}

.install-progress__track {
  height: 6px;
  border-radius: 3px;
  background: var(--border-color);
  overflow: hidden;
}

.install-progress__fill {
  height: 100%;
  border-radius: 3px;
  background: var(--primary);
  transition: width 0.3s ease;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
