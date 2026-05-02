<template>
  <BaseModal
    :show="show"
    :title="title"
    size="small"
    @close="handleCancel"
  >
    <div class="confirm-content">
      <div v-if="icon" class="confirm-icon" :class="`confirm-icon--${type}`">
        <svg v-if="type === 'danger'" width="44" height="44" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="type === 'warning'" width="44" height="44" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
          <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
        <svg v-else width="44" height="44" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.6"/>
          <path d="M12 7h.01" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
          <path d="M12 11v5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
      </div>
      <p v-if="message" class="confirm-message">{{ message }}</p>
      <p v-if="description" class="confirm-description">{{ description }}</p>
      <div v-if="$slots.extra" class="confirm-extra">
        <slot name="extra" />
      </div>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="loading" @click="handleCancel">
        {{ cancelText }}
      </AppButton>
      <AppButton
        :variant="confirmButtonVariant"
        size="md"
        :disabled="loading"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ loading ? loadingText : confirmText }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue';
import AppButton from '../ui/AppButton.vue';

export default {
  name: 'ConfirmModal',
  components: {
    BaseModal,
    AppButton
  },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    title: {
      type: String,
      default: 'Confirm Action'
    },
    message: {
      type: String,
      default: ''
    },
    description: {
      type: String,
      default: ''
    },
    type: {
      type: String,
      default: 'info',
      validator: (value) => ['info', 'warning', 'danger'].includes(value)
    },
    confirmText: {
      type: String,
      default: 'Confirm'
    },
    cancelText: {
      type: String,
      default: 'Cancel'
    },
    loadingText: {
      type: String,
      default: 'Processing...'
    },
    icon: {
      type: Boolean,
      default: true
    },
    loading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['confirm', 'cancel', 'close'],
  computed: {
    confirmButtonVariant() {
      if (this.type === 'danger') return 'danger';
      if (this.type === 'warning') return 'warning';
      return 'primary';
    }
  },
  methods: {
    handleConfirm() {
      if (!this.loading) {
        this.$emit('confirm');
      }
    },
    handleCancel() {
      if (!this.loading) {
        this.$emit('cancel');
        this.$emit('close');
      }
    }
  }
}
</script>

<style scoped>
.confirm-content {
  text-align: center;
  padding: var(--space-3) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.confirm-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-2);
}

.confirm-icon--info    { color: var(--primary); }
.confirm-icon--warning { color: var(--warning); }
.confirm-icon--danger  { color: var(--danger); }

.confirm-message {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  line-height: var(--leading-tight);
}

.confirm-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-normal);
  max-width: 36em;
}

.confirm-extra {
  margin-top: var(--space-3);
  text-align: left;
  width: 100%;
}

:deep(.confirm-checkbox) {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

:deep(.confirm-checkbox) input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--primary);
  cursor: pointer;
}

:deep(.confirm-checkbox) input[type="checkbox"]:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
