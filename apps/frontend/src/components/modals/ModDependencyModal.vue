<template>
  <BaseModal
    :show="show"
    title="Missing dependencies"
    size="medium"
    @close="$emit('cancel')"
  >
    <div class="dep-banner">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" />
        <path d="M12 10V14M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <div>
        <p class="dep-banner__title">This mod lists required dependencies you do not have installed</p>
        <p class="dep-banner__text">
          <strong>{{ mainModTitle }}</strong> requires the following. You can install them automatically or
          continue with only the main mod (the server may not run correctly).
        </p>
      </div>
    </div>

    <ul v-if="missingDeps.length" class="dep-list" role="list">
      <li v-for="(dep, index) in missingDeps" :key="dep.modId || index">
        {{ dep.modTitle || dep.modId }}
      </li>
    </ul>

    <template #footer>
      <AppButton variant="ghost" size="md" @click="$emit('cancel')">
        Cancel
      </AppButton>
      <AppButton variant="ghost" size="md" @click="$emit('install-main-only')">
        Install mod only
      </AppButton>
      <AppButton variant="primary" size="md" @click="$emit('install-with-deps')">
        Install with dependencies
      </AppButton>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'

export default {
  name: 'ModDependencyModal',
  components: { BaseModal, AppButton },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    mainModTitle: {
      type: String,
      default: ''
    },
    missingDeps: {
      type: Array,
      default: () => []
    }
  },
  emits: ['cancel', 'install-main-only', 'install-with-deps']
}
</script>

<style scoped>
.dep-banner {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  border: 1px solid color-mix(in oklch, var(--warning) 35%, transparent);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
}

.dep-banner svg {
  flex-shrink: 0;
  color: var(--warning);
}

.dep-banner__title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.dep-banner__text {
  margin: 0;
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.dep-list {
  margin: 0;
  padding-left: var(--space-5);
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.6;
}

.dep-list li {
  margin-bottom: var(--space-1);
}
</style>
