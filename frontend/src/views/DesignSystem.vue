<script setup>
import AppButton from '../components/ui/AppButton.vue'

const colorTokens = [
  { name: '--bg-primary', value: '#0f0f0f' },
  { name: '--bg-secondary', value: '#141414' },
  { name: '--bg-tertiary', value: '#1a1a1a' },
  { name: '--border-color', value: '#1e1e1e' },
  { name: '--text-primary', value: '#f1f1f1' },
  { name: '--text-secondary', value: '#d4d4d4' },
  { name: '--text-muted', value: '#888' },
  { name: '--text-disabled', value: '#555' },
  { name: '--primary', value: '#f97316' },
  { name: '--success', value: '#22c55e' },
  { name: '--warning', value: '#fbbf24' },
  { name: '--danger', value: '#ef4444' }
]

const radiusTokens = [
  { name: '--radius-sm' },
  { name: '--radius-md' },
  { name: '--radius-lg' },
  { name: '--radius-pill' }
]
</script>

<template>
  <div class="design-system">
    <header class="ds-header">
      <h1>Fabricator Design System</h1>
      <p>Phase 1 visual verification — primitives, tokens, modal.</p>
    </header>
    <section class="ds-section">
      <h2 class="ds-section-title">Tokens</h2>
      <div class="ds-token-grid">
        <div v-for="t in colorTokens" :key="t.name" class="ds-token">
          <div class="ds-token-swatch" :style="{ background: `var(${t.name})` }"></div>
          <div class="ds-token-meta">
            <code>{{ t.name }}</code>
            <span>{{ t.value }}</span>
          </div>
        </div>
      </div>
      <div class="ds-radii">
        <div v-for="r in radiusTokens" :key="r.name" class="ds-radius-box" :style="{ borderRadius: `var(${r.name})` }">
          <code>{{ r.name }}</code>
        </div>
      </div>
    </section>
    <section class="ds-section">
      <h2 class="ds-section-title">AppButton</h2>
      <div class="ds-row">
        <AppButton variant="primary">Start</AppButton>
        <AppButton variant="ghost">Restart</AppButton>
        <AppButton variant="danger">Delete</AppButton>
      </div>
      <div class="ds-row">
        <AppButton variant="primary" size="sm">Save</AppButton>
        <AppButton variant="ghost" size="sm">Cancel</AppButton>
      </div>
      <div class="ds-row">
        <AppButton variant="primary" loading>Installing</AppButton>
        <AppButton variant="primary" disabled>Disabled</AppButton>
      </div>
    </section>
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

.ds-section {
  margin-bottom: var(--space-8);
}

.ds-section-title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
  letter-spacing: -0.2px;
}

.ds-token-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.ds-token {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.ds-token-swatch {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  flex-shrink: 0;
}

.ds-token-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ds-token-meta code {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.ds-token-meta span {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.ds-radii {
  display: flex;
  gap: var(--space-3);
}

.ds-radius-box {
  width: 80px;
  height: 80px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ds-radius-box code {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.ds-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-3);
}
</style>
