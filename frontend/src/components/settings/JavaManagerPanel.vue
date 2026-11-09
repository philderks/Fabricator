<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { getInstalledJava, installJava, getJavaInstallProgress, uninstallJava } from '../../api/servers'
import { useToast } from '../../composables/useToast'
import { formatList, t } from '../../i18n'

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

// Bulk selection, as on the Mods page.
const selectedMajors = ref(new Set())
const bulkConfirmOpen = ref(false)

const installedMajors = computed(() => managed.value.map((item) => item.major))

// No server runs on these or would start on them (#109).
const unusedMajors = computed(() =>
  managed.value.filter((item) => !item.used_by?.length).map((item) => item.major)
)

const allSelected = computed(() =>
  managed.value.length > 0 && managed.value.every((item) => selectedMajors.value.has(item.major))
)

const selectAllLabel = computed(() => {
  if (allSelected.value) return t('java.deselectAll')
  if (selectedMajors.value.size > 0) return t('java.selected', { n: selectedMajors.value.size })
  return t('java.selectAll', managed.value.length)
})

const majorsLabel = (majors) => formatList(majors.map((major) => String(major)))

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
      return t('java.extracting')
    case 'downloading':
      return t('java.downloadingProgress', {
        done: formatMb(downloaded.value),
        total: formatMb(total.value),
        pct: progressPercent.value
      })
    default:
      return t('java.starting')
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
    // Drop selections whose runtime is gone (removed here or elsewhere).
    selectedMajors.value = new Set([...selectedMajors.value].filter((major) => installedMajors.value.includes(major)))
    if (!availableMajors.value.includes(selectedMajor.value)) {
      selectedMajor.value = availableMajors.value[0] ?? null
    }
  } catch (err) {
    error.value = err?.message || t('java.loadFailed')
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
      toast.error(task.error || t('java.installFailed'), t('java.title'))
      resetInstallState()
      return
    }
    if (task.status === 'cancelled') {
      clearPoll()
      toast.warning(t('java.installCancelled'), t('java.title'))
      resetInstallState()
      return
    }
    if (task.status === 'done') {
      clearPoll()
      const major = task.install_major || installMajor.value
      resetInstallState()
      toast.success(t('java.installed', { major }), t('java.title'))
      await loadInstalled()
    }
  } catch (err) {
    clearPoll()
    toast.error(err?.message || t('java.lostContact'), t('java.title'))
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
    toast.error(err?.message || t('java.startFailed'), t('java.title'))
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
    toast.success(t('java.removed', { major }), t('java.title'))
    await loadInstalled()
  } catch (err) {
    toast.error(err?.message || t('java.removeFailed', { major }), t('java.title'))
  } finally {
    deleting.value = false
    deleteTarget.value = null
  }
}

const toggleSelection = (major) => {
  const next = new Set(selectedMajors.value)
  if (next.has(major)) next.delete(major)
  else next.add(major)
  selectedMajors.value = next
}

const toggleSelectAll = () => {
  selectedMajors.value = allSelected.value ? new Set() : new Set(installedMajors.value)
}

// One at a time through the single-remove route; a failure doesn't stop the rest.
const confirmBulkRemove = async () => {
  const majors = [...selectedMajors.value].sort((a, b) => a - b)
  const failed = []
  deleting.value = true
  for (const major of majors) {
    try {
      await uninstallJava(major)
    } catch {
      failed.push(major)
    }
  }
  if (failed.length) {
    toast.error(t('java.removeFailed', { major: majorsLabel(failed) }), t('java.title'))
  } else {
    toast.success(t('java.removed', { major: majorsLabel(majors) }), t('java.title'))
  }
  deleting.value = false
  bulkConfirmOpen.value = false
  selectedMajors.value = new Set()
  await loadInstalled()
}

const versionLabel = (entry) => {
  if (entry.version != null && entry.version !== entry.major) {
    return t('java.versionReports', { major: entry.major, version: entry.version })
  }
  return t('java.version', { major: entry.major })
}

onMounted(loadInstalled)
onBeforeUnmount(clearPoll)
</script>

<template>
  <Panel :title="$t('java.title')">
    <template #action>
      <button
        type="button"
        class="java-manager__refresh"
        :disabled="loading || installing"
        @click="loadInstalled"
      >
        {{ $t('common.refresh') }}
      </button>
    </template>

    <div v-if="loading" class="java-manager__state">{{ $t('java.loading') }}</div>

    <div v-else-if="error" class="java-manager__state java-manager__state--error">
      {{ error }}
    </div>

    <template v-else>
      <div
        v-if="managed.length > 0"
        class="java-manager__bulk-bar"
        :class="{ 'is-active': selectedMajors.size > 0 }"
      >
        <label class="java-manager__select-all">
          <input
            type="checkbox"
            class="java-manager__checkbox"
            :checked="allSelected"
            :indeterminate.prop="selectedMajors.size > 0 && !allSelected"
            @change="toggleSelectAll"
          />
          <span>{{ selectAllLabel }}</span>
        </label>
        <div class="java-manager__bulk-actions">
          <button
            v-if="selectedMajors.size === 0 && unusedMajors.length > 0"
            type="button"
            class="java-manager__bulk-clear"
            @click="selectedMajors = new Set(unusedMajors)"
          >
            {{ $t('java.selectUnused', unusedMajors.length) }}
          </button>
          <template v-if="selectedMajors.size > 0">
            <button type="button" class="java-manager__bulk-clear" @click="selectedMajors = new Set()">
              {{ $t('common.clear') }}
            </button>
            <AppButton
              variant="danger"
              size="sm"
              :disabled="installing"
              :loading="deleting"
              @click="bulkConfirmOpen = true"
            >
              {{ $t('java.removeCount', selectedMajors.size) }}
            </AppButton>
          </template>
        </div>
      </div>

      <ul class="java-manager__list">
        <li
          v-if="systemJava && systemJava.installed"
          class="java-manager__row"
        >
          <div class="java-manager__info">
            <span class="java-manager__title">
              {{ $t('java.systemJava') }}<template v-if="systemJava.version"> {{ systemJava.version }}</template>
            </span>
            <span class="java-manager__path">{{ $t('java.onPath', { path: systemJava.path }) }}</span>
          </div>
          <span class="java-manager__badge">{{ $t('java.systemBadge') }}</span>
        </li>

        <li
          v-for="entry in managed"
          :key="entry.major"
          class="java-manager__row"
        >
          <label class="java-manager__check" :aria-label="$t('java.select', { major: entry.major })">
            <input
              type="checkbox"
              class="java-manager__checkbox"
              :checked="selectedMajors.has(entry.major)"
              @change="toggleSelection(entry.major)"
            />
          </label>
          <div class="java-manager__info">
            <span class="java-manager__title">{{ versionLabel(entry) }}</span>
            <span class="java-manager__path" :title="entry.path">{{ entry.path }}</span>
            <span v-if="entry.used_by?.length" class="java-manager__usage">
              {{ $t('java.usedBy', { servers: formatList(entry.used_by) }) }}
            </span>
          </div>
          <div class="java-manager__actions">
            <span v-if="!entry.used_by?.length" class="java-manager__badge">{{ $t('java.unusedBadge') }}</span>
            <AppButton
              variant="danger"
              size="sm"
              :disabled="installing"
              @click="requestDelete(entry)"
            >
              {{ $t('common.remove') }}
            </AppButton>
          </div>
        </li>

        <li
          v-if="managed.length === 0 && !(systemJava && systemJava.installed)"
          class="java-manager__state"
        >
          {{ $t('java.none') }}
        </li>
      </ul>

      <div class="java-manager__install">
        <template v-if="installing">
          <div class="java-manager__progress-text">
            <span>{{ $t('java.installing', { major: installMajor }) }}</span>
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
            {{ $t('java.addRuntime') }}
          </label>
          <div class="java-manager__install-controls">
            <select
              id="java-install-major"
              v-model.number="selectedMajor"
              class="java-manager__select"
              :disabled="availableMajors.length === 0"
            >
              <option v-if="availableMajors.length === 0" :value="null">
                {{ $t('java.allInstalled') }}
              </option>
              <option
                v-for="major in availableMajors"
                :key="major"
                :value="major"
              >
                {{ $t('java.version', { major }) }}
              </option>
            </select>
            <AppButton
              variant="primary"
              size="sm"
              :disabled="selectedMajor == null"
              @click="startInstall"
            >
              {{ $t('common.install') }}
            </AppButton>
          </div>
        </template>
      </div>
    </template>

    <ConfirmModal
      :show="!!deleteTarget"
      :title="$t('java.removeTitle')"
      :message="deleteTarget ? $t('java.removeMessage', { major: deleteTarget.major }) : ''"
      :description="$t('java.removeDescription')"
      type="danger"
      :confirm-text="$t('common.remove')"
      :loading="deleting"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <ConfirmModal
      :show="bulkConfirmOpen"
      :title="$t('java.removeSelectedTitle')"
      :message="$t('java.removeMessage', { major: majorsLabel([...selectedMajors].sort((a, b) => a - b)) })"
      :description="$t('java.removeDescription')"
      type="danger"
      :confirm-text="$t('java.removeCount', selectedMajors.size)"
      :loading="deleting"
      @confirm="confirmBulkRemove"
      @cancel="bulkConfirmOpen = false"
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
  flex: 1;
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

.java-manager__usage {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.java-manager__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* Bulk bar and checkboxes match the Mods page's. */
.java-manager__bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-3);
  min-height: 44px;
  /* The background bleeds into the panel padding so the checkbox and buttons
     line up with the rows below. */
  margin: 0 calc(-1 * var(--space-3));
  padding: var(--space-2) var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  transition: background 0.15s ease;
}

.java-manager__bulk-bar.is-active {
  background: color-mix(in srgb, var(--primary) 8%, var(--bg-secondary));
}

.java-manager__select-all,
.java-manager__check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  user-select: none;
}

.java-manager__checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--primary);
}

.java-manager__bulk-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.java-manager__bulk-clear {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  padding: 4px 10px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.java-manager__bulk-clear:hover {
  color: var(--text-secondary);
  border-color: var(--text-muted);
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
