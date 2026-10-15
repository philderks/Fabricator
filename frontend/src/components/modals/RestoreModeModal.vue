<script setup>
import { computed, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { t, te } from '../../i18n'

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
  if (!phase) return t('common.working')
  const key = `backups.restore.phase.${phase}`
  return te(key) ? t(key) : phase
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
    :title="$t('backups.restore.title')"
    size="medium"
    :close-on-escape="!restoreActive"
    @close="onCancel"
  >
    <div class="restore-modal">
      <div v-if="restoreActive" class="restore-modal__progress">
        <div class="restore-modal__progress-spinner" aria-hidden="true"></div>
        <p class="restore-modal__progress-label">{{ phaseLabel }}</p>
        <p class="restore-modal__progress-hint">{{ $t('backups.restore.runningHint') }}</p>
      </div>

      <template v-else>
        <i18n-t v-if="props.snapshot" keypath="backups.restore.confirmMessage" tag="p" class="restore-modal__intro">
          <template #name><code>{{ props.snapshot.fileName || props.snapshot.id }}</code></template>
        </i18n-t>
        <p class="restore-modal__sub">{{ $t('backups.restore.safetyHint') }}</p>

        <fieldset class="restore-modal__options">
          <legend class="restore-modal__legend">{{ $t('backups.restore.chooseMode') }}</legend>

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
              <div class="restore-modal__option-title">{{ $t('backups.restore.inPlace') }}</div>
              <div class="restore-modal__option-desc">{{ $t('backups.restore.inPlaceDescription') }}</div>
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
              <div class="restore-modal__option-title">{{ $t('backups.restore.reset') }}</div>
              <i18n-t keypath="backups.restore.resetDescription" tag="div" class="restore-modal__option-desc">
                <template #warning><strong>{{ $t('backups.restore.resetWarning') }}</strong></template>
              </i18n-t>
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
        {{ restoreActive ? $t('backups.restore.inProgress') : $t('common.cancel') }}
      </AppButton>
      <AppButton
        :variant="mode === 'reset' ? 'danger' : 'primary'"
        size="md"
        :disabled="confirmDisabled"
        :loading="restoreActive"
        @click="onConfirm"
      >
        {{ restoreActive ? $t('backups.restore.restoring') : (mode === 'reset' ? $t('backups.restore.reset') : $t('backups.restore.restore')) }}
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
