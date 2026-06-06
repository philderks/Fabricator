<script setup>
import { computed, onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import JavaManagerPanel from '../../components/settings/JavaManagerPanel.vue'
import { version as appVersion } from '../../../package.json'
import { getUpdateStatus } from '../../api/servers'

// Mirror the sidebar's update pill: show the backend's reported version
// (which may be "unknown" on dev checkouts without a .fabricator_version
// file) and fall back to the bundled package.json version only if absent.
const reportedVersion = ref(null)
const displayVersion = computed(() => reportedVersion.value || appVersion)

onMounted(async () => {
  try {
    const status = await getUpdateStatus()
    reportedVersion.value = status?.currentVersion ?? null
  } catch {
    // Non-critical: leave the bundled version as the fallback.
  }
})
</script>

<template>
  <div class="general-settings">
    <JavaManagerPanel />

    <Panel title="About">
      <dl class="general-settings__about">
        <div class="general-settings__about-row">
          <dt>Version</dt>
          <dd>{{ displayVersion }}</dd>
        </div>
        <div class="general-settings__about-row">
          <dt>Application</dt>
          <dd>Fabricator</dd>
        </div>
      </dl>
    </Panel>
  </div>
</template>

<style scoped>
.general-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 880px;
}

.general-settings__about {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.general-settings__about-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.general-settings__about-row dt {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.general-settings__about-row dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-family: var(--font-mono, ui-monospace, monospace);
}
</style>
