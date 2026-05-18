<script setup>
import { computed, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  },
  snapshot: {
    type: Object,
    default: null
  },
  /** Active job state (passed in) so we can show progress + lock during restore. */
  activeJob: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['confirm', 'cancel'])

// Selected mode — `null` until the user picks one. The Confirm button stays
// disabled while mode is null (plan §8 explicit requirement).
const mode = ref(null)

watch(
  () => props.show,
  (open) => {
    if (open) mode.value = null
  }
)

const restoreActive = computed(
  () => props.activeJob?.kind === 'restore' && props.activeJob?.active
)

const phaseLabel = computed(() => {
  const phase = props.activeJob?.phase
  if (!phase) return 'Working…'
  switch (phase) {
    case 'starting':       return 'Starting restore…'
    case 'stopping_server':return 'Stopping server…'
    case 'safety_snapshot':return 'Creating safety snapshot…'
    case 'extracting':     return 'Extracting archive…'
    case 'overlaying':     return 'Overlaying files…'
    case 'swapping':       return 'Swapping server directory…'
    case 'finalizing':     return 'Finalizing…'
    case 'restarting':     return 'Restarting server…'
    case 'done':           return 'Done.'
    case 'failed':         return 'Failed.'
    default:               return phase
  }
})

const confirmDisabled = computed(() => !mode.value || restoreActive.value)

function selectMode(value) {
  if (restoreActive.value) return
  mode.value = value
}

function onConfirm() {
  if (confirmDisabled.value) return
  emit('confirm', mode.value)
}

function onCancel() {
  if (restoreActive.value) return
  emit('cancel')
}
</script>

<template>
  <BaseModal
    :show="props.show"
    title="Restore snapshot"
    size="medium"
    :close-on-escape="!restoreActive"
    @close="onCancel"
  >
    <div class="restore-modal">
      <div v-if="restoreActive" class="restore-modal__progress">
        <div class="restore-modal__progress-spinner" aria-hidden="true"></div>
        <p class="restore-modal__progress-label">{{ phaseLabel }}</p>
        <p class="restore-modal__progress-hint">
          Restore is running in the background. A safety snapshot was created before any files were overwritten.
        </p>
      </div>

      <template v-else>
        <p v-if="props.snapshot" class="restore-modal__intro">
          Restore <code>{{ props.snapshot.fileName || props.snapshot.id }}</code>?
        </p>
        <p class="restore-modal__sub">
          A safety snapshot is always created first, so you can roll back if the restored
          state is unusable.
        </p>

        <fieldset class="restore-modal__options">
          <legend class="restore-modal__legend">Choose restore mode</legend>

          <label
            class="restore-modal__option"
            :class="{ 'is-active': mode === 'in_place' }"
          >
            <input
              type="radio"
              name="restore-mode"
              value="in_place"
              :checked="mode === 'in_place'"
              @change="selectMode('in_place')"
            />
            <div class="restore-modal__option-body">
              <div class="restore-modal__option-title">In-place overlay</div>
              <div class="restore-modal__option-desc">
                Files in the archive overwrite the live server. Files that exist only on
                the live server are kept. Lower risk; new files added since the snapshot
                survive.
              </div>
            </div>
          </label>

          <label
            class="restore-modal__option restore-modal__option--danger"
            :class="{ 'is-active': mode === 'reset' }"
          >
            <input
              type="radio"
              name="restore-mode"
              value="reset"
              :checked="mode === 'reset'"
              @change="selectMode('reset')"
            />
            <div class="restore-modal__option-body">
              <div class="restore-modal__option-title">Reset to snapshot</div>
              <div class="restore-modal__option-desc">
                Atomically swap the server directory with the snapshot contents.
                <strong>Anything added since the snapshot will be permanently removed</strong>
                — only the safety snapshot can bring it back.
              </div>
            </div>
          </label>
        </fieldset>
      </template>
    </div>

    <template #footer>
      <AppButton
        variant="ghost"
        size="md"
        :disabled="restoreActive"
        @click="onCancel"
      >
        {{ restoreActive ? 'Restore in progress' : 'Cancel' }}
      </AppButton>
      <AppButton
        :variant="mode === 'reset' ? 'danger' : 'primary'"
        size="md"
        :disabled="confirmDisabled"
        :loading="restoreActive"
        @click="onConfirm"
      >
        {{ restoreActive ? 'Restoring…' : (mode === 'reset' ? 'Reset to snapshot' : 'Restore') }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.restore-modal {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-2) 0;
}

.restore-modal__intro {
  margin: 0;
  font-size: var(--text-md);
  color: var(--text-primary);
}

.restore-modal__intro code {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--primary);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.restore-modal__sub {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.restore-modal__options {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border: none;
  padding: 0;
  margin: 0;
}

.restore-modal__legend {
  padding: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.restore-modal__option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.restore-modal__option:hover {
  border-color: var(--text-disabled);
}

.restore-modal__option.is-active {
  border-color: var(--primary);
  background: var(--bg-secondary);
}

.restore-modal__option--danger.is-active {
  border-color: var(--danger);
}

.restore-modal__option input[type="radio"] {
  margin-top: 2px;
  accent-color: var(--primary);
  flex-shrink: 0;
}

.restore-modal__option--danger.is-active input[type="radio"] {
  accent-color: var(--danger);
}

.restore-modal__option-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.restore-modal__option-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.restore-modal__option-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.restore-modal__option-desc strong {
  color: var(--danger);
  font-weight: 600;
}

.restore-modal__progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) 0;
  text-align: center;
}

.restore-modal__progress-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: restore-spin 0.7s linear infinite;
}

@keyframes restore-spin {
  to { transform: rotate(360deg); }
}

.restore-modal__progress-label {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
}

.restore-modal__progress-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  max-width: 36em;
}
</style>
