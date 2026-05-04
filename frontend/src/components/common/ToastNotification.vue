<template>
  <div class="toast" :class="[type, { 'toast-exit': isExiting }]">
    <div class="toast-icon">
      <!-- Success Icon -->
      <svg v-if="type === 'success'" width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
        <path d="M8 12L11 15L16 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      
      <!-- Error Icon -->
      <svg v-else-if="type === 'error'" width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
        <path d="M12 7V13M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      
      <!-- Warning Icon -->
      <svg v-else-if="type === 'warning'" width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      
      <!-- Info Icon -->
      <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
        <path d="M12 11V16M12 8H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
    </div>
    
    <div class="toast-content">
      <div class="toast-title" v-if="title">{{ title }}</div>
      <div class="toast-message">{{ message }}</div>
    </div>
    
    <button class="toast-close" @click="$emit('close')" v-if="!autoClose">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
        <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
</template>

<script>
export default {
  name: 'ToastNotification',
  props: {
    type: {
      type: String,
      default: 'info',
      validator: (value) => ['success', 'error', 'warning', 'info'].includes(value)
    },
    title: {
      type: String,
      default: ''
    },
    message: {
      type: String,
      required: true
    },
    autoClose: {
      type: Boolean,
      default: true
    },
    duration: {
      type: Number,
      default: 4000
    }
  },
  emits: ['close'],
  data() {
    return {
      isExiting: false,
      timer: null
    }
  },
  mounted() {
    if (this.autoClose) {
      this.timer = setTimeout(() => {
        this.close()
      }, this.duration)
    }
  },
  beforeUnmount() {
    if (this.timer) {
      clearTimeout(this.timer)
    }
  },
  methods: {
    close() {
      this.isExiting = true
      setTimeout(() => {
        this.$emit('close')
      }, 220) // Match animation duration
    }
  }
}
</script>

<style scoped>
.toast {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  min-width: 320px;
  max-width: 420px;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22), 0 0 0 1px rgba(255, 255, 255, 0.05);
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.toast.toast-exit {
  animation: toast-exit 0.22s ease-in;
  opacity: 0;
  transform: translateY(-0.75rem);
}

.toast-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}

.toast.success .toast-icon {
  color: var(--success);
}

.toast.error .toast-icon {
  color: var(--danger);
}

.toast.warning .toast-icon {
  color: var(--warning);
}

.toast.info .toast-icon {
  color: var(--primary);
}

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.toast-message {
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.4;
  word-wrap: break-word;
}

.toast-close {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
  margin-top: 2px;
}

.toast-close:hover {
  color: var(--text-primary);
}

@keyframes toast-exit {
  from {
    opacity: 1;
    transform: translateY(0);
  }
  to {
    opacity: 0;
    transform: translateY(-0.75rem);
  }
}
</style>
