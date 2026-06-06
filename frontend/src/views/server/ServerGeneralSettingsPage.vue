<script setup>
import { reactive, watch } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import AppButton from '../../components/ui/AppButton.vue'
import { version as appVersion } from '../../../package.json'
import { useToast } from '../../composables/useToast'

const STORAGE_KEY = 'fabricator:preferences'

const DEFAULTS = {
  consoleAutoScroll: true,
  consoleTimestamps: true,
  confirmDestructive: true,
  reducedMotion: false,
  compactSidebar: false
}

const toast = useToast()

const loadPreferences = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULTS }
  }
}

const prefs = reactive(loadPreferences())

watch(
  prefs,
  (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    } catch {
      // localStorage may be unavailable (private mode); preferences are
      // non-critical so we silently skip persistence.
    }
  },
  { deep: true }
)

const resetPreferences = () => {
  Object.assign(prefs, DEFAULTS)
  toast.success('Preferences reset to defaults', 'Settings')
}
</script>

<template>
  <div class="general-settings">
    <Panel title="Console">
      <div class="general-settings__toggles">
        <ToggleRow
          v-model="prefs.consoleAutoScroll"
          label="Auto-scroll to newest output"
        />
        <ToggleRow
          v-model="prefs.consoleTimestamps"
          label="Show timestamps in console"
        />
      </div>
    </Panel>

    <Panel title="Interface">
      <div class="general-settings__toggles">
        <ToggleRow
          v-model="prefs.compactSidebar"
          label="Compact sidebar"
        />
        <ToggleRow
          v-model="prefs.reducedMotion"
          label="Reduce motion and animations"
        />
      </div>
    </Panel>

    <Panel title="Safety">
      <div class="general-settings__toggles">
        <ToggleRow
          v-model="prefs.confirmDestructive"
          label="Ask for confirmation before destructive actions"
        />
      </div>
    </Panel>

    <Panel title="About">
      <dl class="general-settings__about">
        <div class="general-settings__about-row">
          <dt>Version</dt>
          <dd>{{ appVersion }}</dd>
        </div>
        <div class="general-settings__about-row">
          <dt>Application</dt>
          <dd>Fabricator</dd>
        </div>
      </dl>
    </Panel>

    <footer class="general-settings__footer">
      <AppButton variant="ghost" @click="resetPreferences">
        Reset to defaults
      </AppButton>
    </footer>
  </div>
</template>

<style scoped>
.general-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 880px;
}

.general-settings__toggles {
  display: flex;
  flex-direction: column;
  gap: 0;
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

.general-settings__footer {
  display: flex;
  justify-content: flex-end;
}
</style>
