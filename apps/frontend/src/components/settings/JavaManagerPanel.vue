<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { getInstalledJava, installJava, getJavaInstallProgress, uninstallJava } from '../../api/servers'
import { useToast } from '../../composables/useToast'

const toast = useToast()

// Common LTS / Minecraft-relevant majors offered for installation. Adoptium
// does not ship 16 (mapped to 17 server-side), so it is intentionally omitted.
const INSTALLABLE_MAJORS = [8, 11, 17, 21, 25]

const loading = ref(true)
const error = ref('')
const managed = ref([])
const systemJava = ref(null)

const selectedMajor = ref(null)
const installing = ref(false)
const installMajor = ref(null)
const downloaded = ref(0)
const total = ref(0)
const installStatus = ref('')
let pollHandle = null

const deleteTarget = ref(null)
const deleting = ref(false)

const installedMajors = computed(() => managed.value.map((item) => item.major))

const availableMajors = computed(() =>
  INSTALLABLE_MAJORS.filter((major) => !installedMajors.value.includes(major))
)

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

const installStatusLabel = computed(() => {
  switch (installStatus.value) {
    case 'installing':
      return 'Extracting…'
    case 'downloading':
      return `Downloading ${formatMb(downloaded.value)} of ${formatMb(total.value)} (${progressPercent.value}%)`
    default:
      return 'Starting…'
  }
})

const clearPoll = () => {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
}

const resetInstallState = () => {
  clearPoll()
  installing.value = false
  installMajor.value = null
  downloaded.value = 0
  total.value = 0
  installStatus.value = ''
}

const loadInstalled = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await getInstalledJava()
    managed.value = Array.isArray(data?.managed) ? data.managed : []
    systemJava.value = data?.system || null
    if (!availableMajors.value.includes(selectedMajor.value)) {
      selectedMajor.value = availableMajors.value[0] ?? null
    }
  } catch (err) {
    error.value = err?.message || 'Failed to load installed Java runtimes.'
  } finally {
    loading.value = false
  }
}

const pollProgress = async (taskId) => {
  try {
    const task = await getJavaInstallProgress(taskId)
    downloaded.value = task.downloaded || 0
    total.value = task.total || total.value
    installStatus.value = task.status || installStatus.value
    if (task.status === 'error') {
      clearPoll()
      toast.error(task.error || 'The Java install failed.', 'Java')
      resetInstallState()
      return
    }
    if (task.status === 'cancelled') {
      clearPoll()
      toast.warning('Java install was cancelled.', 'Java')
      resetInstallState()
      return
    }
    if (task.status === 'done') {
      clearPoll()
      const major = task.install_major || installMajor.value
      resetInstallState()
      toast.success(`Java ${major} installed.`, 'Java')
      await loadInstalled()
    }
  } catch (err) {
    clearPoll()
    toast.error(err?.message || 'Lost contact with the install task.', 'Java')
    resetInstallState()
  }
}

const startInstall = async () => {
  if (selectedMajor.value == null || installing.value) return
  const major = selectedMajor.value
  installing.value = true
  installMajor.value = major
  downloaded.value = 0
  total.value = 0
  installStatus.value = 'queued'
  try {
    const res = await installJava(major)
    if (res.install_major) installMajor.value = res.install_major
    clearPoll()
    pollHandle = setInterval(() => pollProgress(res.task_id), 750)
  } catch (err) {
    toast.error(err?.message || 'Failed to start Java install.', 'Java')
    resetInstallState()
  }
}

const requestDelete = (entry) => {
  deleteTarget.value = entry
}

const cancelDelete = () => {
  deleteTarget.value = null
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  const major = deleteTarget.value.major
  deleting.value = true
  try {
    await uninstallJava(major)
    toast.success(`Java ${major} removed.`, 'Java')
    await loadInstalled()
  } catch (err) {
    toast.error(err?.message || `Failed to remove Java ${major}.`, 'Java')
  } finally {
    deleting.value = false
    deleteTarget.value = null
  }
}

const versionLabel = (entry) => {
  if (entry.version != null && entry.version !== entry.major) {
    return `Java ${entry.major} (reports ${entry.version})`
  }
  return `Java ${entry.major}`
}

onMounted(loadInstalled)
onBeforeUnmount(clearPoll)
</script>

<template>
  <Panel title="Java">
    <template #action>
      <button
        type="button"
        class="java-manager__refresh"
        :disabled="loading || installing"
        @click="loadInstalled"
      >
        Refresh
      </button>
    </template>

    <div v-if="loading" class="java-manager__state">Loading Java runtimes…</div>

    <div v-else-if="error" class="java-manager__state java-manager__state--error">
      {{ error }}
    </div>

    <template v-else>
      <ul class="java-manager__list">
        <li
          v-if="systemJava && systemJava.installed"
          class="java-manager__row"
        >
          <div class="java-manager__info">
            <span class="java-manager__title">
              System Java<template v-if="systemJava.version"> {{ systemJava.version }}</template>
            </span>
            <span class="java-manager__path">On PATH ({{ systemJava.path }})</span>
          </div>
          <span class="java-manager__badge">System</span>
        </li>

        <li
          v-for="entry in managed"
          :key="entry.major"
          class="java-manager__row"
        >
          <div class="java-manager__info">
            <span class="java-manager__title">{{ versionLabel(entry) }}</span>
            <span class="java-manager__path" :title="entry.path">{{ entry.path }}</span>
          </div>
          <AppButton
            variant="danger"
            size="sm"
            :disabled="installing"
            @click="requestDelete(entry)"
          >
            Remove
          </AppButton>
        </li>

        <li
          v-if="managed.length === 0 && !(systemJava && systemJava.installed)"
          class="java-manager__state"
        >
          No Java runtimes installed yet.
        </li>
      </ul>

      <div class="java-manager__install">
        <template v-if="installing">
          <div class="java-manager__progress-text">
            <span>Installing Java {{ installMajor }}</span>
            <span class="java-manager__progress-status">{{ installStatusLabel }}</span>
          </div>
          <div class="java-manager__progress-track">
            <div
              class="java-manager__progress-fill"
              :style="{ width: progressPercent + '%' }"
            ></div>
          </div>
        </template>

        <template v-else>
          <label class="java-manager__install-label" for="java-install-major">
            Add a Java runtime
          </label>
          <div class="java-manager__install-controls">
            <select
              id="java-install-major"
              v-model.number="selectedMajor"
              class="java-manager__select"
              :disabled="availableMajors.length === 0"
            >
              <option v-if="availableMajors.length === 0" :value="null">
                All common versions installed
              </option>
              <option
                v-for="major in availableMajors"
                :key="major"
                :value="major"
              >
                Java {{ major }}
              </option>
            </select>
            <AppButton
              variant="primary"
              size="sm"
              :disabled="selectedMajor == null"
              @click="startInstall"
            >
              Install
            </AppButton>
          </div>
        </template>
      </div>
    </template>

    <ConfirmModal
      :show="!!deleteTarget"
      title="Remove Java runtime?"
      :message="deleteTarget ? `Remove Java ${deleteTarget.major}?` : ''"
      description="Servers that need this version will prompt you to reinstall it the next time they start."
      type="danger"
      confirm-text="Remove"
      cancel-text="Cancel"
      :loading="deleting"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </Panel>
</template>

<style scoped>
.java-manager__refresh {
  background: none;
  border: none;
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s ease;
}

.java-manager__refresh:hover:not(:disabled) {
  color: var(--text-secondary);
}

.java-manager__refresh:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.java-manager__state {
  color: var(--text-muted);
  font-size: var(--text-sm);
  padding: var(--space-2) 0;
}

.java-manager__state--error {
  color: var(--danger);
}

.java-manager__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.java-manager__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-color);
}

.java-manager__row:last-child {
  border-bottom: none;
}

.java-manager__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.java-manager__title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.java-manager__path {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono, ui-monospace, monospace);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.java-manager__badge {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
}

.java-manager__install {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-color);
}

.java-manager__install-label {
  display: block;
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: var(--space-2);
}

.java-manager__install-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.java-manager__select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 10px;
  font-family: inherit;
  font-size: var(--text-sm);
  min-width: 200px;
}

.java-manager__select:focus {
  outline: none;
  border-color: var(--primary);
}

.java-manager__select:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.java-manager__progress-text {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
}

.java-manager__progress-status {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.java-manager__progress-track {
  height: 6px;
  border-radius: var(--radius-sm);
  background: var(--border-color);
  overflow: hidden;
}

.java-manager__progress-fill {
  height: 100%;
  border-radius: var(--radius-sm);
  background: var(--primary);
  transition: width 0.3s ease;
}
</style>
