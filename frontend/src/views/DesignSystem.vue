<script setup>
</script>

<template>
  <div class="design-system">
    <header class="ds-header">
      <h1>Fabricator Design System</h1>
      <p>Phase 1 visual verification — primitives, tokens, modal.</p>
    </header>
    <!-- Sections added by later tasks -->
  </div>
</template>

<style scoped>
.design-system {
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 32px 40px;
  font-family: var(--font-sans, system-ui);
}

.ds-header {
  margin-bottom: 32px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.ds-header h1 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.5px;
  margin: 0 0 4px;
}

.ds-header p {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}
</style>
