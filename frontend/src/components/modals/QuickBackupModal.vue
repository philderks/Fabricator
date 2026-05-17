<script setup>
import { ref, watch, computed } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  },
  activeJob: {
    type: Object,
    default: null
  },
  defaultStoragePath: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['confirm', 'cancel'])

const storagePath = ref('')
const compress = ref(true)
const flush = ref(true)
const shutdown = ref(false)
const localError = ref(null)

watch(
  () => props.show,
  (open) => {
    if (open) {
      storagePath.value = props.defaultStoragePath
      compress.value = true
      flush.value = true
      shutdown.value = false
      localError.value = null
    }
  }
)

const jobActive = computed(() => props.activeJob?.active)

function onConfirm() {
  localError.value = null
  emit('confirm', { storagePath: storagePath.value.trim(), compress: compress.value, flush: flush.value, shutdown: shutdown.value })
}

function onCancel() {
  if (jobActive.value) return
  emit('cancel')
}
</script>

<template>
  <BaseModal
    :show="props.show"
    title="Quick backup"
    size="small"
    :close-on-escape="!jobActive"
    @close="onCancel"
  >
    <div class="quick-backup-modal">
      <p class="quick-backup-modal__intro">
        Run a one-off backup without creating a config. The archive is written to the path you specify.
      </p>

      <div class="quick-backup-modal__field">
        <label class="quick-backup-modal__label" for="qb-storage-path">Storage path (optional)</label>
        <input
          id="qb-storage-path"
          v-model="storagePath"
          type="text"
          class="quick-backup-modal__input"
          placeholder="/absolute/path/to/backups"
          :disabled="jobActive"
          @keydown.enter="onConfirm"
        />
        <span class="quick-backup-modal__hint">Leave empty to use the server's default backup folder.</span>
      </div>

      <div class="quick-backup-modal__toggles">
        <label class="quick-backup-modal__toggle">
          <input v-model="compress" type="checkbox" :disabled="jobActive" />
          <span class="quick-backup-modal__toggle-label">Compress</span>
          <span class="quick-backup-modal__toggle-hint">Gzip world-data and config files (recommended).</span>
        </label>
        <label class="quick-backup-modal__toggle">
          <input v-model="flush" type="checkbox" :disabled="jobActive" />
          <span class="quick-backup-modal__toggle-label">Flush before backup</span>
          <span class="quick-backup-modal__toggle-hint">Send save-all to the server before copying files.</span>
        </label>
        <label class="quick-backup-modal__toggle">
          <input v-model="shutdown" type="checkbox" :disabled="jobActive" />
          <span class="quick-backup-modal__toggle-label">Shut down server</span>
          <span class="quick-backup-modal__toggle-hint">Stop the server for the copy, then restart it.</span>
        </label>
      </div>

      <p v-if="localError" class="quick-backup-modal__error">{{ localError }}</p>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="jobActive" @click="onCancel">
        Cancel
      </AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="jobActive"
        :loading="jobActive"
        @click="onConfirm"
      >
        {{ jobActive ? 'Backing up…' : 'Start quick backup' }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.quick-backup-modal {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-1) 0;
}

.quick-backup-modal__intro {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.quick-backup-modal__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.quick-backup-modal__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.quick-backup-modal__input {
  width: 100%;
  box-sizing: border-box;
  padding: 6px var(--space-3);
  font: inherit;
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s ease;
}

.quick-backup-modal__input:focus {
  border-color: var(--primary);
}

.quick-backup-modal__input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.quick-backup-modal__hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.quick-backup-modal__toggles {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.quick-backup-modal__toggle {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: var(--space-2);
  row-gap: 2px;
  cursor: pointer;
}

.quick-backup-modal__toggle input[type="checkbox"] {
  grid-row: 1 / 3;
  align-self: start;
  margin-top: 3px;
  accent-color: var(--primary);
  cursor: pointer;
}

.quick-backup-modal__toggle input[type="checkbox"]:disabled {
  cursor: not-allowed;
}

.quick-backup-modal__toggle-label {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 500;
}

.quick-backup-modal__toggle-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.quick-backup-modal__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--danger);
}
</style>
