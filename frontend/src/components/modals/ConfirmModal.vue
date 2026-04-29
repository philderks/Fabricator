<template>
  <BaseModal 
    :show="show" 
    :title="title" 
    size="small"
    @close="handleCancel"
  >
    <div class="confirm-content">
      <div v-if="icon" class="confirm-icon" :class="`confirm-icon-${type}`">
        <svg v-if="type === 'danger'" width="48" height="48" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="type === 'warning'" width="48" height="48" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else width="48" height="48" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <p class="confirm-message">{{ message }}</p>
      <p v-if="description" class="confirm-description">{{ description }}</p>
      <div v-if="$slots.extra" class="confirm-extra">
        <slot name="extra" />
      </div>
    </div>

    <template #footer>
      <button class="btn btn-secondary" @click="handleCancel" :disabled="loading">
        {{ cancelText }}
      </button>
      <button 
        class="btn"
        :class="confirmButtonClass"
        @click="handleConfirm"
        :disabled="loading"
      >
        <span v-if="loading" class="btn-loading"></span>
        {{ loading ? loadingText : confirmText }}
      </button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue';

export default {
  name: 'ConfirmModal',
  components: {
    BaseModal
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
    confirmButtonClass() {
      if (this.type === 'danger') return 'btn-danger';
      if (this.type === 'warning') return 'btn-warning';
      return 'btn-primary';
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
  padding: 12px 0;
}

.confirm-icon {
  margin: 0 auto 20px;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-icon-info {
  color: var(--primary);
}

.confirm-icon-warning {
  color: var(--warning);
}

.confirm-icon-danger {
  color: var(--danger);
}

.confirm-message {
  font-size: 1.125rem;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.confirm-description {
  font-size: 0.9375rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.confirm-extra {
  margin-top: 16px;
  text-align: left;
}

:deep(.confirm-checkbox) {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 0.9375rem;
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

.btn-warning {
  background: var(--warning);
  color: var(--bg-primary);
}

.btn-warning:hover:not(:disabled) {
  background: #d97706;
}
</style>
