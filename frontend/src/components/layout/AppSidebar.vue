<script setup>
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__placeholder">Sidebar (Task 2)</div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 216px;
  min-width: 216px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.app-sidebar__placeholder {
  padding: var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-sm);
}
</style>
