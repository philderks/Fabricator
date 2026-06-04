<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import StatCard from '../../components/ui/StatCard.vue'
import Panel from '../../components/ui/Panel.vue'
import { installedModDisplayName, installedModInitial } from '../../utils/installedModDisplay'
import { useServerStore } from '../../stores/server'
import { usePlayitStore } from '../../stores/playit'

const route = useRoute()
const store = useServerStore()
const playit = usePlayitStore()

/** Matches sidebar Backups nav — always derive :id from the URL to avoid store/route drift. */
const backupsRouteLocation = computed(() => {
  const raw = route.params.id
  const id = typeof raw === 'string' ? raw : raw?.[0]
  return id ? { name: 'ServerBackups', params: { id } } : null
})

const RECENT_LOG_PREVIEW_LINES = 16

const ramUsedDisplay = computed(() => store.ramMetrics.used.toFixed(1))
const ramTotalDisplay = computed(() => store.ramMetrics.total.toFixed(1))
const ramPercent = computed(() => {
  const m = store.ramMetrics
  if (!m.total) return 0
  return Math.round((m.used / m.total) * 100)
})
const cpuPercent = computed(() => {
  const cpu = store.server?.runtime?.cpu
  return typeof cpu === 'number' ? Math.min(100, Math.round(cpu)) : null
})
const cpuDisplay = computed(() => {
  return cpuPercent.value !== null ? `${cpuPercent.value}%` : '—'
})
const recentLogLines = computed(() => {
  const lines = store.logs.stdout || []
  return lines.slice(-RECENT_LOG_PREVIEW_LINES)
})
const modPreview = computed(() => store.installedMods.slice(0, 4))

// ─── playit.gg — Public-IP stat card (per-server, derived from the store) ────
// The full tunnel UI lives in the per-server playit.gg tab; here we only show
// an at-a-glance address card for THIS server's matched tunnel.

const playitTunnel = computed(() => playit.tunnelForPort(store.server?.port))
const playitLive = computed(() =>
  Boolean(playitTunnel.value?.address && !playitTunnel.value?.disabled_reason)
)

const copied = ref(false)
let _copyTimeout = null
let _unsubscribePlayit = null

function copyAddress() {
  const addr = playitTunnel.value?.address
  if (!addr) return
  navigator.clipboard.writeText(addr).then(() => {
    copied.value = true
    if (_copyTimeout) clearTimeout(_copyTimeout)
    _copyTimeout = setTimeout(() => {
      copied.value = false
      _copyTimeout = null
    }, 2000)
  }).catch(() => { /* clipboard unavailable — silent */ })
}

onMounted(() => {
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
    <section class="overview-page__stats" :class="{ 'overview-page__stats--five': playitLive }">
      <StatCard label="Players" :value="store.serverStatus.players.online" :unit="store.serverStatus.players.max ? `/${store.serverStatus.players.max}` : ''" />
      <StatCard label="Uptime" :value="store.serverStatus.uptime" />
      <StatCard label="Version" :value="store.serverStatus.version" />
      <StatCard label="Mods" :value="store.installedMods.length" :accent="store.installedMods.length > 0 ? 'primary' : 'default'" />

      <!-- Public IP card — only rendered when THIS server's tunnel is live -->
      <div v-if="playitLive" class="stat-playit">
        <div class="stat-playit__label">
          <!-- Globe icon -->
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/>
            <line x1="2" y1="12" x2="22" y2="12"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
          Public IP
        </div>
        <div class="stat-playit__value">
          <span class="stat-playit__addr" :title="playitTunnel.address">{{ playitTunnel.address }}</span>
          <button
            class="stat-playit__copy"
            :class="{ 'stat-playit__copy--confirmed': copied }"
            type="button"
            :aria-label="copied ? 'Copied!' : 'Copy address'"
            @click="copyAddress"
          >
            <!-- Clipboard icon — shown by default -->
            <svg v-if="!copied" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="9" y="2" width="6" height="4" rx="1"/>
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
            </svg>
            <!-- Check icon — shown for 2 s after copy -->
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </button>
        </div>
      </div>
    </section>

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
              <span class="overview-page__perf-value">{{ ramUsedDisplay }} / {{ ramTotalDisplay }} GB</span>
              <span class="overview-page__perf-pct">{{ ramPercent }}%</span>
            </div>
            <div class="overview-page__bar">
              <div class="overview-page__bar-fill" :style="{ width: ramPercent + '%' }"></div>
            </div>
            <div class="overview-page__perf-row">
              <span class="overview-page__perf-label">CPU</span>
              <span class="overview-page__perf-value">{{ cpuDisplay }}</span>
              <span class="overview-page__perf-pct">{{ cpuPercent !== null ? cpuPercent + '%' : '' }}</span>
            </div>
            <div class="overview-page__bar">
              <div class="overview-page__bar-fill overview-page__bar-fill--cpu" :style="{ width: (cpuPercent ?? 0) + '%' }"></div>
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
            <div v-if="!recentLogLines.length" class="overview-page__empty">No logs yet.</div>
            <div v-else v-for="(line, i) in recentLogLines" :key="i" class="overview-page__log-line">
              {{ line }}
            </div>
          </div>
        </Panel>
      </div>

      <div class="overview-page__col">
        <Panel title="Installed mods">
          <template #action>
            <a class="overview-page__panel-link" @click.prevent="store.goToMods">
              Manage
              <svg class="icon-arrow-right" width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 6H7.5M7.5 3.25l3.25 2.75L7.5 8.75" /></svg>
            </a>
          </template>
          <div v-if="!modPreview.length" class="overview-page__empty">No mods installed.</div>
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

        <Panel title="Quick actions">
          <div class="overview-page__qa-grid">
            <router-link
              v-if="backupsRouteLocation"
              class="overview-page__qa"
              :to="backupsRouteLocation"
            >
              <span class="overview-page__qa-title">Backups</span>
              <span class="overview-page__qa-sub">Manage snapshots</span>
            </router-link>
            <button
              v-else
              type="button"
              class="overview-page__qa"
              disabled
            >
              <span class="overview-page__qa-title">Backups</span>
              <span class="overview-page__qa-sub">Manage snapshots</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToConsole">
              <span class="overview-page__qa-title">Console</span>
              <span class="overview-page__qa-sub">View logs</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToSettings">
              <span class="overview-page__qa-title">Properties</span>
              <span class="overview-page__qa-sub">server.properties</span>
            </button>
            <button type="button" class="overview-page__qa" @click="store.goToSettings">
              <span class="overview-page__qa-title">World</span>
              <span class="overview-page__qa-sub">Manage in settings</span>
            </button>
          </div>
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  min-width: 0;
}

/* Expands to 5 equal columns when the Public IP card is present */
.overview-page__stats--five {
  grid-template-columns: repeat(5, minmax(0, 1fr));
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

.overview-page__qa-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.overview-page__qa {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: inherit;
  font-family: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.overview-page__qa:hover:not(:disabled) {
  border-color: var(--text-disabled);
}

.overview-page__qa:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.overview-page__qa:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.overview-page__qa-title {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.overview-page__qa-sub {
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.icon-arrow-right {
  flex-shrink: 0;
  display: block;
  vertical-align: middle;
}

/* ─── Public IP (playit) stat card ─────────────────────────────────────── */
/* Matches StatCard's visual design token-for-token; built inline because
   StatCard has no slot for icons or interactive controls. */

.stat-playit {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  min-width: 0;
}

.stat-playit__label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-disabled);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.stat-playit__value {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-width: 0;
}

.stat-playit__addr {
  /* Smaller than StatCard's 22px value — the address is long text, not a number */
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text-primary);
  letter-spacing: -0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.stat-playit__copy {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.12s ease, background 0.12s ease, border-color 0.12s ease;
}

.stat-playit__copy:hover {
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.stat-playit__copy:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Confirmed state: briefly tint the check green */
.stat-playit__copy--confirmed {
  color: var(--success);
}
</style>
