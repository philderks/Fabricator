<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast-list" tag="div" class="toast-list">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-anchor"
        >
          <ToastNotification
            :type="toast.type"
            :title="toast.title"
            :message="toast.message"
            :duration="toast.duration"
            :auto-close="toast.autoClose"
            :action="toast.action"
            @close="removeToast(toast.id)"
          />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import ToastNotification from './ToastNotification.vue'
import { useToast } from '../../composables/useToast'

const { toasts, removeToast } = useToast()
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: max(0.75rem, env(safe-area-inset-top, 0px));
  left: 0;
  right: 0;
  z-index: 9999;
  padding: 0 1rem;
  box-sizing: border-box;
  pointer-events: none;
}

.toast-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.toast-anchor {
  display: flex;
  justify-content: center;
  width: 100%;
  pointer-events: none;
}

.toast-anchor > * {
  pointer-events: auto;
}

/* TransitionGroup: slide from above, quieter than corner fly-in */
.toast-list-move,
.toast-list-enter-active,
.toast-list-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.toast-list-enter-from {
  opacity: 0;
  transform: translateY(calc(-100% - 0.75rem));
}

.toast-list-leave-to {
  opacity: 0;
  transform: translateY(-0.75rem);
}

.toast-list-leave-active {
  position: absolute;
  left: 0;
  right: 0;
  width: 100%;
  display: flex;
  justify-content: center;
  box-sizing: border-box;
}

@media (max-width: 768px) {
  .toast-container {
    padding: 0 max(1rem, env(safe-area-inset-right, 0px)) 0
      max(1rem, env(safe-area-inset-left, 0px));
  }

  .toast-container :deep(.toast) {
    min-width: 0;
    max-width: none;
    width: 100%;
  }

}
</style>
