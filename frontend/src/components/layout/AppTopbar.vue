<script setup>
</script>

<template>
  <header class="app-topbar">
    <div class="app-topbar__placeholder">Topbar (Task 4)</div>
  </header>
</template>

<style scoped>
.app-topbar {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.app-topbar__placeholder {
  color: var(--text-muted);
  font-size: var(--text-sm);
}
</style>
