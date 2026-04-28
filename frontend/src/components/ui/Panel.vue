<script setup>
defineProps({
  title: {
    type: String,
    default: ''
  },
  padded: {
    type: Boolean,
    default: true
  }
})
</script>

<template>
  <section class="panel">
    <header v-if="title || $slots.action" class="panel__header">
      <span v-if="title" class="panel__title">{{ title }}</span>
      <div v-if="$slots.action" class="panel__action">
        <slot name="action" />
      </div>
    </header>
    <div class="panel__body" :class="{ 'panel__body--flush': !padded }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
}

.panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-color);
}

.panel__title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.panel__action {
  font-size: var(--text-xs);
}

.panel__body {
  padding: var(--space-4);
}

.panel__body--flush {
  padding: 0;
}
</style>
