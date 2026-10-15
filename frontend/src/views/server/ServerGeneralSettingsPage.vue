<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import JavaManagerPanel from '../../components/settings/JavaManagerPanel.vue'
import McpPanel from '../../components/settings/McpPanel.vue'
import ChangePasswordPanel from '../../components/settings/ChangePasswordPanel.vue'
import PasswordTogglePanel from '../../components/settings/PasswordTogglePanel.vue'
import { useAuthStore } from '../../stores/auth'
import { useServerStore } from '../../stores/server'
import { usePreferencesStore } from '../../stores/preferences'
import { version as appVersion } from '../../../package.json'
import { getUpdateStatus } from '../../api/servers'
import { availableSettingsSections, settingsSectionLabel } from '../../utils/settingsSections'

const auth = useAuthStore()
const store = useServerStore()
const prefs = usePreferencesStore()
const route = useRoute()

// This page serves two routes: /server/:id/settings and the server-less
// /settings. Read the param rather than store.currentServerId — the store keeps
// the last server it saw, and only ServerLayout resyncs it, so on /settings it
// would still be set. Standalone also has no AppTopbar, hence its own heading
// and padding (RootLayout leaves both to the page, like Servers.vue).
const hasServer = computed(() => Boolean(route.params.id))

// Everything except About lives behind its own sub-page, so the index is a
// short menu rather than one long scroll of unrelated panels.
const sections = computed(() => availableSettingsSections({
  hasServer: hasServer.value,
  managed: auth.managed,
  authEnabled: auth.enabled
}))

// Only honour a section that exists in this context: a hand-typed or stale URL
// (say /settings/java under managed mode) falls back to the index rather than
// rendering a blank page.
const activeSection = computed(() => {
  const key = route.params.section
  return sections.value.some((s) => s.key === key) ? key : null
})

const sectionTo = (key) => (hasServer.value
  ? { name: 'ServerGeneralSettings', params: { id: route.params.id, section: key } }
  : { name: 'GlobalSettings', params: { section: key } })

// Back to the index. Passing an empty section is what clears the optional param.
const indexTo = computed(() => (hasServer.value
  ? { name: 'ServerGeneralSettings', params: { id: route.params.id, section: '' } }
  : { name: 'GlobalSettings', params: { section: '' } }))

const activeSectionLabel = computed(() => settingsSectionLabel(activeSection.value))

const DOCS_URL = 'https://docs.fabricator.site'
// The tracker itself, not a prefilled new issue: it lands on existing reports
// first, so a duplicate can be found before it is filed.
const ISSUES_URL = 'https://github.com/philderks/Fabricator/issues'

// Boot auto-start mode — saves instantly via its own endpoint, so it stays
// editable even while the server is running (unlike server.properties).
// `label` and `hint` are i18n keys.
const autoStartOptions = [
  {
    value: 'always',
    label: 'settings.autostart.always',
    hint: 'settings.autostart.alwaysHint',
  },
  {
    value: 'last',
    label: 'settings.autostart.last',
    hint: 'settings.autostart.lastHint',
  },
  {
    value: 'never',
    label: 'settings.autostart.never',
    hint: 'settings.autostart.neverHint',
  },
]

// Mirror the sidebar's update pill: show the backend's reported version
// (which may be "unknown" on dev checkouts without a .fabricator_version
// file) and fall back to the bundled package.json version only if absent.
const reportedVersion = ref(null)
const displayVersion = computed(() => reportedVersion.value || appVersion)

onMounted(async () => {
  // Managed: skip the one-shot self-update probe (gate-denied); the bundled
  // version stays the displayed fallback.
  if (auth.managed) return
  try {
    const status = await getUpdateStatus()
    reportedVersion.value = status?.currentVersion ?? null
  } catch {
    // Non-critical: leave the bundled version as the fallback.
  }
})
</script>

<template>
  <div class="general-settings" :class="{ 'general-settings--standalone': !hasServer }">
    <!-- The server route gets its breadcrumb from AppTopbar; RootLayout has no
         topbar, so the server-less route carries its own. -->
    <nav v-if="!hasServer" class="general-settings__heading" :aria-label="$t('common.breadcrumb')">
      <template v-if="activeSection">
        <router-link :to="indexTo" class="general-settings__crumb-link">{{ $t('nav.settings') }}</router-link>
        <span class="general-settings__crumb-sep" aria-hidden="true">/</span>
        <!-- The h1 tracks the deepest crumb, so the page keeps a real heading
             rather than trading it for breadcrumb markup. -->
        <h1 class="general-settings__title" aria-current="page">{{ activeSectionLabel }}</h1>
      </template>
      <h1 v-else class="general-settings__title">{{ $t('nav.settings') }}</h1>
    </nav>

    <!-- Keyed on the section so navigating swaps the element rather than
         patching it in place, which is what lets the entrance below replay.
         The breadcrumb above stays put — it is the fixed part of the frame. -->
    <div class="general-settings__view" :key="activeSection || 'index'">
    <!-- Index: the sub-pages, then About inline. -->
    <template v-if="!activeSection">
      <Panel :padded="false">
        <nav class="general-settings__menu" :aria-label="$t('settings.sectionsLabel')">
          <router-link
            v-for="section in sections"
            :key="section.key"
            :to="sectionTo(section.key)"
            class="general-settings__menu-item"
          >
            <span class="general-settings__menu-text">
              <span class="general-settings__menu-label">{{ $t(section.label) }}</span>
              <span class="general-settings__menu-desc">{{ $t(section.description) }}</span>
            </span>
            <svg class="general-settings__menu-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M5.5 3l4 4-4 4" />
            </svg>
          </router-link>
        </nav>
      </Panel>

      <Panel :title="$t('settings.help')" :padded="false">
        <div class="general-settings__menu">
          <a
            class="general-settings__menu-item"
            :href="DOCS_URL"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="general-settings__menu-text">
              <span class="general-settings__menu-label">{{ $t('settings.docs') }}</span>
              <span class="general-settings__menu-desc">{{ $t('settings.docsDescription') }}</span>
            </span>
            <svg class="general-settings__menu-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4.5 1.5H10.5V7.5" />
              <path d="M10.5 1.5L5 7" />
              <path d="M9 8v2.5H1.5V3H4" />
            </svg>
          </a>
          <a
            class="general-settings__menu-item"
            :href="ISSUES_URL"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="general-settings__menu-text">
              <span class="general-settings__menu-label">{{ $t('settings.issues') }}</span>
              <span class="general-settings__menu-desc">{{ $t('settings.issuesDescription') }}</span>
            </span>
            <svg class="general-settings__menu-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4.5 1.5H10.5V7.5" />
              <path d="M10.5 1.5L5 7" />
              <path d="M9 8v2.5H1.5V3H4" />
            </svg>
          </a>
        </div>
      </Panel>

      <Panel :title="$t('settings.about')">
        <dl class="general-settings__about">
          <div class="general-settings__about-row">
            <dt>{{ $t('settings.version') }}</dt>
            <dd>{{ displayVersion }}</dd>
          </div>
          <div class="general-settings__about-row">
            <dt>{{ $t('settings.application') }}</dt>
            <dd>Fabricator</dd>
          </div>
        </dl>
      </Panel>
    </template>

    <Panel v-if="activeSection === 'autostart'" :title="$t('settings.sections.autostart')">
      <p class="general-settings__autostart-intro">{{ $t('settings.autostart.intro') }}</p>
      <div class="general-settings__autostart" role="radiogroup" :aria-label="$t('settings.autostart.modeLabel')">
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
            <span class="general-settings__autostart-label">{{ $t(opt.label) }}</span>
            <span class="general-settings__autostart-hint">{{ $t(opt.hint) }}</span>
          </span>
        </label>
      </div>
    </Panel>

    <Panel v-if="activeSection === 'display'" :title="$t('settings.sections.display')">
      <ToggleRow
        :model-value="prefs.memoryUnit === 'MB'"
        :label="$t('settings.display.ramMb')"
        :hint="$t('settings.display.ramMbHint')"
        @update:model-value="prefs.memoryUnit = $event ? 'MB' : 'GB'"
      />
      <ToggleRow
        :model-value="prefs.cpuDisplayMode === 'total'"
        :label="$t('settings.display.cpuTotal')"
        :hint="$t('settings.display.cpuTotalHint')"
        @update:model-value="prefs.cpuDisplayMode = $event ? 'total' : 'average'"
      />
      <ToggleRow
        v-model="prefs.showHeapStats"
        :label="$t('settings.display.heapStats')"
        :hint="$t('settings.display.heapStatsHint')"
      />
    </Panel>

    <JavaManagerPanel v-if="activeSection === 'java'" />

    <McpPanel v-if="activeSection === 'mcp'" />

    <!-- Nothing to change when there is no password; the toggle panel below
         covers that state and is how one gets set again. -->
    <ChangePasswordPanel v-if="activeSection === 'security' && auth.enabled" />

    <PasswordTogglePanel v-if="activeSection === 'security'" />
    </div>
  </div>
</template>

<style scoped>
.general-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 880px;
  /* A flex item's auto margins absorb the leftover cross-axis space, so this
     centers the reading column instead of it hugging the sidebar edge with a
     growing dead zone on wide/ultrawide monitors. */
  margin: 0 auto;
}

/* RootLayout supplies no padding and no topbar, so the server-less route
   carries both itself (matching Servers.vue's --space-5). */
.general-settings--standalone {
  padding: var(--app-content-padding);
}

.general-settings__heading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

/* Holds the panel stack so the wrapper doesn't swallow the parent's column
   gap, and gives the index <-> sub-page swap an entrance. User-initiated and
   always a full content change, which is exactly when motion helps. */
.general-settings__view {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  animation: settings-view-in 180ms ease-out both;
}

@keyframes settings-view-in {
  from { opacity: 0; transform: translateY(3px); }
  to   { opacity: 1; transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  .general-settings__view {
    animation: none;
  }
}

.general-settings__title {
  margin: 0;
  font-size: inherit;
  font-weight: inherit;
  color: inherit;
}

.general-settings__crumb-link {
  color: var(--text-muted);
  text-decoration: none;
  transition: color 0.15s ease;
}

.general-settings__crumb-link:hover {
  color: var(--primary);
}

.general-settings__crumb-sep {
  color: var(--text-disabled);
  font-weight: 400;
}

/* ---------- Index menu ---------- */

.general-settings__menu {
  display: flex;
  flex-direction: column;
}

.general-settings__menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid var(--border-color);
  transition: background 0.15s ease;
}

/* The panel already draws the closing edge. */
.general-settings__menu-item:last-child {
  border-bottom: none;
}

.general-settings__menu-item:hover {
  background: var(--bg-tertiary);
}

.general-settings__menu-item:hover .general-settings__menu-chevron {
  color: var(--primary);
  transform: translateX(2px);
}

.general-settings__menu-item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.general-settings__menu-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.general-settings__menu-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.general-settings__menu-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.general-settings__menu-chevron {
  flex-shrink: 0;
  color: var(--text-disabled);
  transition: color 0.15s ease, transform 0.15s ease;
}

@media (prefers-reduced-motion: reduce) {
  .general-settings__menu-chevron {
    transition: none;
  }
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
