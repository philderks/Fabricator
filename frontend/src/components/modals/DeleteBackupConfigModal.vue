<script setup>
import { computed, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { formatFileSize } from '../../utils/format'

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  },
  config: {
    type: Object,
    default: null
  },
  /** snapshots owned by this config, used to compute the purge stats. */
  configSnapshots: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['confirm', 'cancel'])

// Purge checkbox — UNCHECKED BY DEFAULT per plan §6 + §8 (Purge UX, no
// silent orphans). When false, the parent's API call omits `?purge=1` and
// retained files are surfaced via a banner on the page.
const purge = ref(false)

watch(
  () => props.show,
  (open) => {
    if (open) purge.value = false
  }
)

const fileCount = computed(() => props.configSnapshots.length)
const totalBytes = computed(() =>
  props.configSnapshots.reduce(
    (acc, snap) => acc + (typeof snap.sizeBytes === 'number' ? snap.sizeBytes : 0),
    0
  )
)
const totalLabel = computed(() => formatFileSize(totalBytes.value))

function onConfirm() {
  if (props.loading) return
  emit('confirm', { purge: purge.value })
}

function onCancel() {
  if (props.loading) return
  emit('cancel')
}
</script>

<template>
  <BaseModal
    :show="props.show"
    :title="$t('backups.deleteConfig.title')"
    size="small"
    :close-on-escape="!props.loading"
    @close="onCancel"
  >
    <div class="delete-config">
      <div class="delete-config__icon" aria-hidden="true">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
      </div>
      <i18n-t keypath="backups.deleteConfig.message" tag="p" class="delete-config__message">
        <template #name><strong>{{ props.config?.name || $t('backups.deleteConfig.thisConfig') }}</strong></template>
      </i18n-t>
      <p class="delete-config__description">{{ $t('backups.deleteConfig.description') }}</p>

      <label class="delete-config__purge">
        <input
          type="checkbox"
          v-model="purge"
          :disabled="props.loading || fileCount === 0"
        />
        <span class="delete-config__purge-body">
          <span class="delete-config__purge-title">
            {{ $t('backups.deleteConfig.purge', fileCount) }}
            <span v-if="fileCount > 0" class="delete-config__purge-size">({{ totalLabel }})</span>
          </span>
          <span class="delete-config__purge-sub">
            <template v-if="fileCount === 0">{{ $t('backups.deleteConfig.nothingToPurge') }}</template>
            <template v-else>{{ $t('backups.deleteConfig.retainHint') }}</template>
          </span>
        </span>
      </label>
    </div>

    <template #footer>
      <AppButton
        variant="ghost"
        size="md"
        :disabled="props.loading"
        @click="onCancel"
      >
        {{ $t('common.cancel') }}
      </AppButton>
      <AppButton
        variant="danger"
        size="md"
        :loading="props.loading"
        :disabled="props.loading"
        @click="onConfirm"
      >
        {{ props.loading ? $t('common.deletingEllipsis') : (purge ? $t('backups.deleteConfig.confirmWithFiles') : $t('backups.deleteConfig.confirm')) }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.delete-config {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  text-align: center;
  padding: var(--space-3) 0;
}

.delete-config__icon {
  color: var(--danger);
  margin-bottom: var(--space-2);
}

.delete-config__message {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
}

.delete-config__description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  max-width: 36em;
}

.delete-config__purge {
  margin-top: var(--space-3);
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  width: 100%;
  text-align: left;
  padding: var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  cursor: pointer;
}

.delete-config__purge input[type="checkbox"] {
  margin-top: 2px;
  width: 16px;
  height: 16px;
  accent-color: var(--danger);
  cursor: pointer;
  flex-shrink: 0;
}

.delete-config__purge input[type="checkbox"]:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.delete-config__purge-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.delete-config__purge-title {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 500;
}

.delete-config__purge-size {
  color: var(--text-muted);
  font-weight: 400;
  margin-left: 4px;
}

.delete-config__purge-sub {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}
</style>
