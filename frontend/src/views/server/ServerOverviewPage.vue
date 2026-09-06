<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import StatCard from '../../components/ui/StatCard.vue'
import Panel from '../../components/ui/Panel.vue'
import { installedModDisplayName, installedModInitial } from '../../utils/installedModDisplay'
import { useServerStore } from '../../stores/server'
import { usePlayitStore } from '../../stores/playit'
import { useAuthStore } from '../../stores/auth'
import { usePreferencesStore } from '../../stores/preferences'
import { copyToClipboard } from '../../utils/clipboard'
import { contentLabel } from '../../utils/loaderKind'

const store = useServerStore()
const playit = usePlayitStore()
const prefs = usePreferencesStore()
const auth = useAuthStore()

// "Mods" vs "Plugins" for the installed-content panel, per loader.
const contentNoun = computed(() => contentLabel(store.server?.loader, true))
const contentNounLower = computed(() => contentNoun.value.toLowerCase())

const RECENT_LOG_PREVIEW_LINES = 16

// ramMetrics is always in GB; the Overview memory-unit preference only changes
// how we present it here (GB with one decimal, or whole MB).
const ramUnitLabel = computed(() => prefs.memoryUnit)
const formatRam = (gb) =>
  prefs.memoryUnit === 'MB' ? String(Math.round(gb * 1024)) : gb.toFixed(1)
const ramUsedDisplay = computed(() => formatRam(store.ramMetrics.used))
const ramTotalDisplay = computed(() => formatRam(store.ramMetrics.total))
const ramPercent = computed(() => {
  const m = store.ramMetrics
  if (!m.total) return 0
  return Math.round((m.used / m.total) * 100)
})
// Backend reports the raw process CPU% (can exceed 100 on multi-core hosts)
// plus the host core count. We mirror the RAM row — a used/total pair plus a
// utilization percent — and let the setting choose the units.
const cpuCores = computed(() => {
  const cores = store.server?.runtime?.cpuCores
  return typeof cores === 'number' && cores > 0 ? cores : 1
})
const cpuRaw = computed(() => {
  const cpu = store.server?.runtime?.cpu
  return typeof cpu === 'number' ? cpu : null
})
// Utilization as a 0–100% share of total capacity: identical in both modes,
// drives the bar, and reads 0% (not blank) when idle or stopped.
const cpuPercent = computed(() => Math.round((cpuRaw.value ?? 0) / cpuCores.value))
// Left-hand "used / total" figures, in the units the current mode reports:
// total mode counts every core (e.g. 250% / 400%), average mode is 0–100%.
const cpuUsedDisplay = computed(() =>
  prefs.cpuDisplayMode === 'total'
    ? Math.round(cpuRaw.value ?? 0)
    : cpuPercent.value
)
const cpuTotalDisplay = computed(() =>
  prefs.cpuDisplayMode === 'total' ? cpuCores.value * 100 : 100
)
// Cap the bar fill at 100% so it never overflows.
const cpuBarWidth = computed(() => Math.min(100, cpuPercent.value))
const recentLogLines = computed(() => {
  const lines = store.logs.stdout || []
  // Entries are { ts, text }; tolerate plain strings from an older backend.
  return lines
    .slice(-RECENT_LOG_PREVIEW_LINES)
    .map((entry) => (typeof entry === 'string' ? entry : (entry?.text ?? '')))
})
const modPreview = computed(() => store.installedMods.slice(0, 4))

// ─── playit.gg — public address for THIS server's matched tunnel ────────────
// The full tunnel UI lives in the per-server playit.gg tab; here it is one row
// of the Connection panel, beside the local address.

const playitTunnel = computed(() => playit.tunnelForPort(store.server?.port))
const playitLive = computed(() =>
  Boolean(playitTunnel.value?.address && !playitTunnel.value?.disabled_reason)
)

// TPS is the number that says whether the server is keeping up — CPU% does not.
// null whenever the runtime isn't reporting it (stopped, or not yet sampled).
const tpsDisplay = computed(() => {
  const tps = store.serverStatus.tps
  return typeof tps === 'number' ? tps.toFixed(1) : '—'
})

// Minecraft counts 20 ticks a second, so anything at or near 20 is healthy and
// a sustained drop is lag players can feel.
const tpsAccent = computed(() => {
  const tps = store.serverStatus.tps
  if (typeof tps !== 'number') return 'default'
  if (tps >= 19) return 'success'
  if (tps >= 15) return 'warning'
  return 'danger'
})

// The LAN/local address: whatever host this page was opened on, plus the
// server's port. A guess, but the right one nearly always — Fabricator and the
// server it manages are the same machine — and it beats the page never
// answering "what do I connect to?" at all. The playit row below is the
// authoritative public address when a tunnel is up.
const localAddress = computed(() => {
  const port = store.server?.port
  if (!port) return ''
  const host = typeof window !== 'undefined' ? window.location.hostname : ''
  if (!host) return ''
  return `${host}:${port}`
})

// Which row last showed "Copied" — one flag per row rather than a shared
// boolean, so copying the public address doesn't flash a tick on the local one.
const copiedKey = ref('')
let _copyTimeout = null
let _unsubscribePlayit = null

async function copyValue(key, value) {
  if (!value) return
  const ok = await copyToClipboard(value)
  if (!ok) return
  copiedKey.value = key
  if (_copyTimeout) clearTimeout(_copyTimeout)
  _copyTimeout = setTimeout(() => {
    copiedKey.value = ''
    _copyTimeout = null
  }, 2000)
}

onMounted(() => {
  if (auth.managed) return
  _unsubscribePlayit = playit.subscribe()
})

onUnmounted(() => {
  if (_unsubscribePlayit) {
    _unsubscribePlayit()
    _unsubscribePlayit = null
  }
  if (_copyTimeout) clearTimeout(_copyTimeout)
})
</script>

<template>
  <div class="overview-page">
    <section class="overview-page__stats">
      <StatCard label="Players" :value="store.serverStatus.players.online" :unit="store.serverStatus.players.max ? `/${store.serverStatus.players.max}` : ''" />
      <StatCard label="Uptime" :value="store.serverStatus.uptime" />
      <StatCard label="TPS" :value="tpsDisplay" :accent="tpsAccent" />
      <StatCard label="Mods" :value="store.installedMods.length" :accent="store.installedMods.length > 0 ? 'primary' : 'default'" />
    </section>

    <!-- Forge/NeoForge run a subprocess installer that can take minutes, during
         which every panel below has nothing real to say. Lead with the install
         rather than leaving a page of zeroes and "no logs yet". -->
    <Panel v-if="store.serverInstalling" title="Installing server">
      <div class="overview-page__install">
        <div class="overview-page__install-head">
          <span class="overview-page__install-label">{{ store.installDisplay.label }}</span>
          <span v-if="store.installDisplay.determinate" class="overview-page__install-pct">
            {{ store.installDisplay.percent }}%
          </span>
        </div>
        <div class="overview-page__bar">
          <div
            class="overview-page__bar-fill"
            :class="{ 'is-indeterminate': !store.installDisplay.determinate }"
            :style="store.installDisplay.determinate
              ? { width: `${store.installDisplay.percent}%` }
              : null"
          ></div>
        </div>
        <p class="overview-page__install-note">
          {{ store.installDisplay.detail || 'This can take a few minutes. You can leave this page — the install keeps running.' }}
        </p>
      </div>
    </Panel>

    <Panel v-if="store.activeModpack" title="Active modpack">
      <div class="overview-page__modpack">
        <span class="overview-page__modpack-name">{{ store.activeModpack.name || store.activeModpack.projectId }}</span>
        <span class="overview-page__modpack-version">{{ store.activeModpack.version }}</span>
      </div>
    </Panel>

    <section class="overview-page__row">
      <div class="overview-page__col">
        <Panel title="Performance">
          <div class="overview-page__perf">
            <div class="overview-page__perf-row">
              <span class="overview-page__perf-label">RAM</span>
              <span class="overview-page__perf-value">{{ ramUsedDisplay }} / {{ ramTotalDisplay }} {{ ramUnitLabel }}</span>
              <span class="overview-page__perf-pct">{{ ramPercent }}%</span>
            </div>
            <div class="overview-page__bar">
              <div class="overview-page__bar-fill" :style="{ width: ramPercent + '%' }"></div>
            </div>
            <div class="overview-page__perf-row">
              <span class="overview-page__perf-label">CPU</span>
              <span class="overview-page__perf-value">{{ cpuUsedDisplay }}% / {{ cpuTotalDisplay }}%</span>
              <span class="overview-page__perf-pct">{{ cpuPercent }}%</span>
            </div>
            <div class="overview-page__bar">
              <div class="overview-page__bar-fill overview-page__bar-fill--cpu" :style="{ width: cpuBarWidth + '%' }"></div>
            </div>
          </div>
        </Panel>

        <Panel title="Recent logs">
          <template #action>
            <a class="overview-page__panel-link" @click.prevent="store.goToConsole">
              Console
              <svg class="icon-arrow-right" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 6H7.5M7.5 3.25l3.25 2.75L7.5 8.75" /></svg>
            </a>
          </template>
          <div class="overview-page__logs">
            <div v-if="!recentLogLines.length" class="overview-page__empty">
              <template v-if="store.serverInstalling">Installing — the server has not started yet.</template>
              <template v-else>No logs yet.</template>
            </div>
            <div v-else v-for="(line, i) in recentLogLines" :key="i" class="overview-page__log-line">
              {{ line }}
            </div>
          </div>
        </Panel>
      </div>

      <div class="overview-page__col">
        <Panel :title="`Installed ${contentNoun}`">
          <template #action>
            <a class="overview-page__panel-link" @click.prevent="store.goToMods">
              Manage
              <svg class="icon-arrow-right" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 6H7.5M7.5 3.25l3.25 2.75L7.5 8.75" /></svg>
            </a>
          </template>
          <div v-if="!modPreview.length" class="overview-page__empty">
            <template v-if="store.backgroundModpackInstalling">{{ store.backgroundModpackLabel }}</template>
            <template v-else-if="store.serverInstalling">Waiting for the install to finish.</template>
            <template v-else>No {{ contentNounLower }} installed.</template>
          </div>
          <ul v-else class="overview-page__mods">
            <li v-for="mod in modPreview" :key="mod.path" class="overview-page__mod">
              <div class="overview-page__mod-main">
                <div class="overview-page__mod-icon" aria-hidden="true">
                  <img
                    v-if="mod.iconUrl"
                    class="overview-page__mod-icon-img"
                    :src="mod.iconUrl"
                    alt=""
                  />
                  <span v-else class="overview-page__mod-icon-letter">{{ installedModInitial(mod) }}</span>
                </div>
                <span class="overview-page__mod-name">{{ installedModDisplayName(mod) }}</span>
              </div>
              <span class="overview-page__mod-version">{{ mod.version }}</span>
            </li>
          </ul>
        </Panel>

        <!-- Replaces the old Quick actions grid, whose four tiles all led to
             pages already one click away in the sidebar (two of them to the
             same page). The address is the thing this page could not answer. -->
        <Panel title="Connection">
          <dl class="overview-page__conn">
            <div v-if="localAddress" class="overview-page__conn-row">
              <dt class="overview-page__conn-label">{{ playitLive ? 'Local' : 'Address' }}</dt>
              <dd class="overview-page__conn-value">
                <code>{{ localAddress }}</code>
                <button
                  type="button"
                  class="overview-page__conn-copy"
                  :class="{ 'is-confirmed': copiedKey === 'local' }"
                  :aria-label="copiedKey === 'local' ? 'Copied' : 'Copy address'"
                  @click="copyValue('local', localAddress)"
                >{{ copiedKey === 'local' ? 'Copied' : 'Copy' }}</button>
              </dd>
            </div>

            <div v-if="playitLive" class="overview-page__conn-row">
              <dt class="overview-page__conn-label">Public</dt>
              <dd class="overview-page__conn-value">
                <code :title="playitTunnel.address">{{ playitTunnel.address }}</code>
                <button
                  type="button"
                  class="overview-page__conn-copy"
                  :class="{ 'is-confirmed': copiedKey === 'public' }"
                  :aria-label="copiedKey === 'public' ? 'Copied' : 'Copy public address'"
                  @click="copyValue('public', playitTunnel.address)"
                >{{ copiedKey === 'public' ? 'Copied' : 'Copy' }}</button>
              </dd>
            </div>

            <div class="overview-page__conn-row">
              <dt class="overview-page__conn-label">Port</dt>
              <dd class="overview-page__conn-value">
                <code>{{ store.server?.port ?? '—' }}</code>
              </dd>
            </div>
          </dl>

          <p class="overview-page__conn-note">
            <template v-if="playitLive">
              Local works on your own network; public works from anywhere.
            </template>
            <template v-else>
              Reachable on your network. For access from outside it, set up a
              tunnel on the playit.gg tab or forward the port on your router.
            </template>
          </p>
        </Panel>
      </div>
    </section>
  </div>
</template>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.overview-page__stats {
  display: grid;
  /* Fixed four: Players, Uptime, TPS, Mods — the values that change. Version
     is carried by the topbar status pill and the server switcher, and the
     public-address card that used to extend this row now lives in the
     Connection panel, so there is no variable count left to accommodate. */
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  min-width: 0;
}

.overview-page__modpack {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.overview-page__modpack-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.overview-page__modpack-version {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.overview-page__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
}

.overview-page__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
}

.overview-page__perf {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.overview-page__perf-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.overview-page__perf-label {
  color: var(--text-secondary);
  flex-shrink: 0;
  min-width: 2.5rem;
}

.overview-page__perf-value {
  color: var(--text-secondary);
  flex: 1;
}

.overview-page__perf-pct {
  color: var(--text-disabled);
  font-size: var(--text-xs);
  flex-shrink: 0;
}

.overview-page__bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.overview-page__bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-pill);
  transition: width 0.3s ease;
}

.overview-page__bar-fill--cpu {
  background: var(--accent, var(--primary));
  opacity: 0.75;
}

/* Phases that report no byte count — notably running_installer, the long one
   on Forge/NeoForge. Motion says "still working" where a 0% bar would not. */
.overview-page__bar-fill.is-indeterminate {
  width: 30%;
  animation: overview-install-slide 1.2s ease-in-out infinite;
}

@keyframes overview-install-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.overview-page__install {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.overview-page__install-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.overview-page__install-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.overview-page__install-pct {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.overview-page__install-note {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
  overflow-wrap: anywhere;
}

@media (prefers-reduced-motion: reduce) {
  .overview-page__bar-fill.is-indeterminate {
    animation: none;
  }
}

.overview-page__panel-link {
  display: inline-flex;
  align-items: center;
  gap: 0.28em;
  font-size: var(--text-xs);
  color: var(--primary);
  cursor: pointer;
  text-decoration: none;
}

.overview-page__panel-link:hover {
  text-decoration: underline;
}

.overview-page__logs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  width: 100%;
  min-height: 14rem;
  max-height: 22rem;
  overflow-x: hidden;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.overview-page__log-line {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.overview-page__empty {
  color: var(--text-disabled);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  padding: var(--space-2) 0;
}

.overview-page__mods {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.overview-page__mod {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}

.overview-page__mod:last-child {
  border-bottom: none;
}

.overview-page__mod-main {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  flex: 1;
}

.overview-page__mod-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.overview-page__mod-icon-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.overview-page__mod-icon-letter {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-muted);
}

.overview-page__mod-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.overview-page__mod-version {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  flex-shrink: 0;
  margin-left: var(--space-3);
}

.overview-page__conn {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.overview-page__conn-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-width: 0;
}

.overview-page__conn-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  flex-shrink: 0;
}

.overview-page__conn-value {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.overview-page__conn-value code {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  /* An address is one token: clip it rather than let it wrap or widen the
     column, and the title attribute carries the full value. */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-page__conn-copy {
  flex-shrink: 0;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.overview-page__conn-copy:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.overview-page__conn-copy:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.overview-page__conn-copy.is-confirmed {
  border-color: var(--success);
  color: var(--success);
}

.overview-page__conn-note {
  margin: var(--space-3) 0 0;
  font-size: var(--text-xs);
  color: var(--text-disabled);
  line-height: var(--leading-normal);
}

.icon-arrow-right {
  flex-shrink: 0;
  display: block;
  vertical-align: middle;
}

/* Mobile: the four/five stat cards and the two content columns are the only
   things on this page that assume width. Two stat columns rather than one —
   the cards are a short label over a short value, so a single column wastes
   most of the row and pushes everything below the fold. */
@media (max-width: 900px) {
  .overview-page__row {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 768px) {
  .overview-page__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

</style>
