<script setup>
import { computed, onMounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import JavaManagerPanel from '../../components/settings/JavaManagerPanel.vue'
import ChangePasswordPanel from '../../components/settings/ChangePasswordPanel.vue'
import { useAuthStore } from '../../stores/auth'
import { useServerStore } from '../../stores/server'
import { usePreferencesStore } from '../../stores/preferences'
import { version as appVersion } from '../../../package.json'
import { getUpdateStatus } from '../../api/servers'

const auth = useAuthStore()
const store = useServerStore()
const prefs = usePreferencesStore()

// Boot auto-start mode — saves instantly via its own endpoint, so it stays
// editable even while the server is running (unlike server.properties).
const autoStartOptions = [
  {
    value: 'always',
    label: 'Always start',
    hint: 'Start this server every time Fabricator starts.',
  },
  {
    value: 'last',
    label: 'Restore last state',
    hint: 'Start only if it was running when Fabricator last stopped — survives crashes and host reboots.',
  },
  {
    value: 'never',
    label: 'Never',
    hint: 'Do not start automatically. Start it manually when you need it.',
  },
]

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
    <Panel v-if="!auth.managed" title="Auto-start">
      <p class="general-settings__autostart-intro">
        What should happen to this server when Fabricator starts up?
      </p>
      <div class="general-settings__autostart" role="radiogroup" aria-label="Auto-start mode">
        <label
          v-for="opt in autoStartOptions"
          :key="opt.value"
          class="general-settings__autostart-option"
          :class="{ 'general-settings__autostart-option--active': store.autoStartMode === opt.value }"
        >
          <input
            type="radio"
            name="autostart-mode"
            :value="opt.value"
            :checked="store.autoStartMode === opt.value"
            @change="store.setAutoStartMode(opt.value)"
          />
          <span class="general-settings__autostart-text">
            <span class="general-settings__autostart-label">{{ opt.label }}</span>
            <span class="general-settings__autostart-hint">{{ opt.hint }}</span>
          </span>
        </label>
      </div>
    </Panel>

    <Panel title="Display">
      <ToggleRow
        :model-value="prefs.memoryUnit === 'MB'"
        label="Show RAM in MB on the Overview"
        hint="Off shows the Overview RAM readout in gigabytes; on shows megabytes. Display only — it does not change how much memory the server is allocated."
        @update:model-value="prefs.memoryUnit = $event ? 'MB' : 'GB'"
      />
      <ToggleRow
        :model-value="prefs.cpuDisplayMode === 'total'"
        label="Show total CPU across all cores"
        hint="Off shows average system load (0–100%, like Task Manager). On shows the raw process usage, which can exceed 100% on multi-core hosts."
        @update:model-value="prefs.cpuDisplayMode = $event ? 'total' : 'average'"
      />
    </Panel>

    <JavaManagerPanel v-if="!auth.managed" />

    <ChangePasswordPanel v-if="auth.enabled" />

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

.general-settings__autostart-intro {
  margin: 0 0 var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.general-settings__autostart {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.general-settings__autostart-option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  cursor: pointer;
  transition: border-color 120ms ease, background 120ms ease;
}

.general-settings__autostart-option:hover {
  border-color: var(--text-muted);
}

.general-settings__autostart-option--active {
  border-color: var(--primary);
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.general-settings__autostart-option input[type="radio"] {
  margin-top: 2px;
  width: 16px;
  height: 16px;
  accent-color: var(--primary);
  cursor: pointer;
  flex-shrink: 0;
}

.general-settings__autostart-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.general-settings__autostart-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.general-settings__autostart-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
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
