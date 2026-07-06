<script setup>
import { ref, watch, computed } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  },
  uploading: {
    type: Boolean,
    default: false
  },
  /** Upload percentage 0–100, or -1 when indeterminate. */
  uploadPct: {
    type: Number,
    default: 0
  },
  activeJob: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['confirm', 'cancel', 'cancel-upload'])

const ACCEPT = '.zip,.tar,.tar.gz,.tgz'

const file = ref(null)
const localError = ref(null)
const fileInput = ref(null)

watch(
  () => props.show,
  (open) => {
    if (open) {
      file.value = null
      localError.value = null
    }
  }
)

const jobActive = computed(() => props.activeJob?.active)
const busy = computed(() => props.uploading || jobActive.value)

const fileSizeLabel = computed(() => {
  if (!file.value) return ''
  const mb = file.value.size / (1024 * 1024)
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`
  return `${mb.toFixed(1)} MB`
})

const indeterminate = computed(() => props.uploadPct < 0)

function looksLikeArchive(name) {
  const lower = name.toLowerCase()
  return lower.endsWith('.zip') || lower.endsWith('.tar')
    || lower.endsWith('.tar.gz') || lower.endsWith('.tgz')
}

function onFileChange(event) {
  const picked = event.target.files?.[0] || null
  if (picked && !looksLikeArchive(picked.name)) {
    localError.value = 'Please choose a .zip, .tar, .tar.gz or .tgz archive.'
    file.value = null
    return
  }
  localError.value = null
  file.value = picked
}

function onConfirm() {
  if (!file.value) {
    localError.value = 'Choose a world archive to import.'
    return
  }
  localError.value = null
  emit('confirm', file.value)
}

function onCancel() {
  if (busy.value) return
  emit('cancel')
}
</script>

<template>
  <BaseModal
    :show="props.show"
    title="Import world"
    size="small"
    :close-on-escape="!busy"
    @close="onCancel"
  >
    <div class="import-world-modal">
      <p class="import-world-modal__intro">
        Upload a world archive (<code>.zip</code>, <code>.tar</code>,
        <code>.tar.gz</code>) to replace this server's active world. Both
        multiplayer worlds and singleplayer saves are accepted — singleplayer
        saves are converted to the server layout automatically.
      </p>

      <!-- Warning: destructive + stops the server -->
      <div class="import-world-modal__warning" role="note">
        <strong>Heads up.</strong> The server is stopped for the import and its
        current world is <strong>replaced</strong>. A safety snapshot of the
        existing world is taken first, so you can restore it from the snapshots
        list if needed.
      </div>

      <div class="import-world-modal__field">
        <label class="import-world-modal__label" for="iw-file">World archive</label>
        <input
          id="iw-file"
          ref="fileInput"
          type="file"
          class="import-world-modal__input"
          :accept="ACCEPT"
          :disabled="busy"
          @change="onFileChange"
        />
        <span v-if="file" class="import-world-modal__hint">
          {{ file.name }} · {{ fileSizeLabel }}
        </span>
      </div>

      <!-- Upload progress (during the upload itself) -->
      <div v-if="uploading" class="import-world-modal__progress">
        <div class="import-world-modal__progress-track">
          <div
            class="import-world-modal__progress-bar"
            :class="{ 'is-indeterminate': indeterminate }"
            :style="indeterminate ? {} : { width: `${uploadPct}%` }"
          ></div>
        </div>
        <span class="import-world-modal__progress-label">
          {{ indeterminate ? 'Uploading…' : `Uploading… ${uploadPct}%` }}
        </span>
      </div>

      <p v-if="localError" class="import-world-modal__error">{{ localError }}</p>
    </div>

    <template #footer>
      <AppButton
        v-if="uploading"
        variant="ghost"
        size="md"
        @click="emit('cancel-upload')"
      >
        Cancel upload
      </AppButton>
      <AppButton v-else variant="ghost" size="md" :disabled="busy" @click="onCancel">
        Cancel
      </AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="busy || !file"
        :loading="busy"
        @click="onConfirm"
      >
        {{ uploading ? 'Uploading…' : jobActive ? 'Importing…' : 'Import & replace world' }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.import-world-modal {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-1) 0;
}

.import-world-modal__intro {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.import-world-modal__intro code {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.import-world-modal__warning {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  border: 1px solid var(--warning-dark);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: rgba(245, 158, 11, 0.07);
}

.import-world-modal__warning strong {
  color: var(--warning);
}

.import-world-modal__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.import-world-modal__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.import-world-modal__input {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.import-world-modal__input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.import-world-modal__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.import-world-modal__progress {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.import-world-modal__progress-track {
  width: 100%;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-tertiary);
  overflow: hidden;
}

.import-world-modal__progress-bar {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-pill);
  transition: width 0.2s ease;
}

.import-world-modal__progress-bar.is-indeterminate {
  width: 40%;
  animation: import-indeterminate 1.1s ease-in-out infinite;
}

@keyframes import-indeterminate {
  0%   { margin-left: -40%; }
  100% { margin-left: 100%; }
}

.import-world-modal__progress-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.import-world-modal__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--danger);
}
</style>
