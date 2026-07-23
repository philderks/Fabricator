<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Panel from '../../components/ui/Panel.vue'
import AppButton from '../../components/ui/AppButton.vue'
import ConfirmModal from '../../components/modals/ConfirmModal.vue'
import { useServerStore } from '../../stores/server'
import { usePlayitStore } from '../../stores/playit'
import { useAuthStore } from '../../stores/auth'
import { copyToClipboard } from '../../utils/clipboard'

const store = useServerStore()
const playit = usePlayitStore()
const auth = useAuthStore()

let _unsubscribePlayit = null

// Tunnels, account and agent approvals all live here. Surfaced persistently in
// the panel header rather than only in the "no tunnel for this port" branch —
// it's the place users go for every playit.gg task, not just that one.
const PLAYIT_DASHBOARD_URL = 'https://playit.gg/account'

// ─── Section A — global tunnel agent ────────────────────────────────────────

// Binary-signature warning: non-blocking, but suppressed when the error state
// already explains a missing binary (no point double-warning).
const showBinaryWarning = computed(() =>
  !playit.binaryVerified
  && !(playit.isError && /binary not found/i.test(playit.errorReason || ''))
)

// ─── Destructive-action confirms (running state only) ───────────────────────
// The agent is SHARED across all servers, so Disable/Reset from any server's
// tab tears it down for everyone. Gate both behind the in-app ConfirmModal
// (CC6: never window.confirm), reusing the promise-resolver pattern.
const confirmConfig = ref(null)
let _confirmResolver = null

function requestConfirm(config) {
  return new Promise((resolve) => {
    _confirmResolver = resolve
    confirmConfig.value = config
  })
}
function handleConfirm() {
  confirmConfig.value = null
  if (_confirmResolver) { _confirmResolver(true); _confirmResolver = null }
}
function handleConfirmCancel() {
  confirmConfig.value = null
  if (_confirmResolver) { _confirmResolver(false); _confirmResolver = null }
}

async function disableTunnel() {
  const ok = await requestConfirm({
    type: 'warning',
    title: 'Disable the playit.gg tunnel?',
    message: 'This stops the shared agent for all servers, not just this one — '
      + 'their public addresses go offline until you re-enable it.',
    confirmText: 'Disable',
    cancelText: 'Keep running',
  })
  if (ok) playit.stop()
}

async function resetTunnel() {
  const ok = await requestConfirm({
    type: 'danger',
    title: 'Reset playit.gg?',
    message: 'This stops the shared agent for all servers and deletes the saved '
      + "account secret — you'll have to re-claim from scratch.",
    confirmText: 'Reset',
    cancelText: 'Cancel',
  })
  if (ok) playit.reset()
}

// ─── Section B — this server's address (per-server, derived) ────────────────

const port = computed(() => {
  const p = Number(store.server?.port)
  return Number.isFinite(p) ? p : null
})
const tunnel = computed(() => (port.value === null ? null : playit.tunnelForPort(port.value)))

// Muted deferral hint shown in Section B while the agent isn't running yet.
const deferralHint = computed(() => {
  switch (playit.status) {
    case 'starting': return 'Agent is connecting…'
    case 'claiming': return 'Finish the playit.gg sign-in above.'
    case 'error':    return 'Resolve the tunnel agent error above.'
    default:         return 'Enable the tunnel agent above to expose this server.'
  }
})

// Copy-with-2s-check, same pattern as the Overview stat card.
const copied = ref(false)
let _copyTimeout = null
async function copyAddress() {
  const addr = tunnel.value?.address
  if (!addr) return
  const ok = await copyToClipboard(addr)
  if (!ok) return
  copied.value = true
  if (_copyTimeout) clearTimeout(_copyTimeout)
  _copyTimeout = setTimeout(() => { copied.value = false; _copyTimeout = null }, 2000)
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
  // Resolve any open confirm so a pending promise doesn't dangle.
  if (_confirmResolver) { _confirmResolver(false); _confirmResolver = null }
})
</script>

<template>
  <div v-if="!auth.managed" class="playit-page">
    <!-- ─── Section A: tunnel agent (global) ─────────────────────────────── -->
    <Panel title="playit.gg tunnel agent">
      <!-- Persistent dashboard link: visible in every agent state, so managing
           tunnels never depends on reaching a particular branch below. -->
      <template v-if="!playit.isUnsupported" #action>
        <a
          :href="PLAYIT_DASHBOARD_URL"
          target="_blank"
          rel="noopener noreferrer"
          class="pa-dashlink"
          aria-label="Open the playit.gg dashboard (opens in a new tab)"
        >
          Dashboard
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </template>

      <!-- unsupported short-circuits everything (Windows) -->
      <p v-if="playit.isUnsupported" class="pa-note">
        playit.gg isn't available on this platform.
      </p>

      <template v-else>
        <p class="pa-scope">
          These controls manage the <strong>shared</strong> playit.gg agent for
          <strong>all</strong> servers, not just this one.
        </p>

        <div v-if="showBinaryWarning" class="pa-warn" role="status">
          playit binary signature unverified — see install logs.
        </div>

        <!-- stopped → benefit-framed CTA -->
        <div v-if="playit.isStopped" class="pa-onboarding">
          <div class="pa-onboarding__text">
            <p class="pa-lead">Make your servers reachable for friends without router setup.</p>
            <p class="pa-sub">playit.gg creates public tunnels — no port forwarding, no firewall changes.</p>
          </div>
          <AppButton variant="primary" @click="playit.start">Enable playit.gg</AppButton>
        </div>

        <!-- error → danger banner + two actions (no confirm: nothing live) -->
        <div v-else-if="playit.isError" class="pa-error-state">
          <div class="pa-error-banner" role="alert">
            <svg class="pa-error-banner__icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <div class="pa-error-banner__text">
              <p class="pa-error-banner__title">playit.gg tunnel agent failed</p>
              <p class="pa-error-banner__reason">{{ playit.errorReason || 'No further details — check the playit.gg dashboard.' }}</p>
            </div>
          </div>
          <div class="pa-actions">
            <AppButton variant="ghost" @click="playit.start">Try again</AppButton>
            <AppButton variant="primary" @click="playit.reset">Use different account</AppButton>
          </div>
        </div>

        <!-- claiming → URL stays surfaced for the whole user-action window -->
        <div v-else-if="playit.isClaiming && playit.claimUrl" class="pa-claiming">
          <div class="pa-claiming__step">
            <span class="pa-claiming__num">1</span>
            <span>Open the link below and sign in to (or sign up for) playit.gg</span>
          </div>
          <a :href="playit.claimUrl" target="_blank" rel="noopener noreferrer" class="pa-claiming__link">
            {{ playit.claimUrl }}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
          <div class="pa-claiming__step">
            <span class="pa-claiming__num">2</span>
            <span>Approve this agent on the playit.gg page — the tunnel activates automatically.</span>
          </div>
          <div class="pa-claiming__actions">
            <button type="button" class="pa-textbtn" @click="playit.stop">Cancel setup</button>
            <button type="button" class="pa-textbtn" @click="playit.reset">Use different account</button>
          </div>
        </div>

        <!-- running → active + destructive controls (both confirmed) -->
        <div v-else-if="playit.isRunning" class="pa-active">
          <span class="pa-active__dot" aria-hidden="true"></span>
          <span class="pa-active__text">Tunnel agent active.</span>
          <div class="pa-active__actions">
            <button type="button" class="pa-pillbtn" @click="disableTunnel">Disable</button>
            <button type="button" class="pa-pillbtn" @click="resetTunnel">Reset</button>
          </div>
        </div>

        <!-- starting (fallback) → quiet connecting + cancel -->
        <div v-else class="pa-starting">
          <span class="pa-starting__dot" aria-hidden="true"></span>
          <span class="pa-starting__text">Connecting tunnel agent…</span>
          <button type="button" class="pa-pillbtn" @click="playit.stop">Cancel</button>
        </div>
      </template>
    </Panel>

    <!-- ─── Section B: this server's public address ──────────────────────── -->
    <Panel v-if="!playit.isUnsupported && port !== null" title="This server's public address">
      <!-- agent not running yet → defer to Section A -->
      <p v-if="!playit.isRunning" class="pb-hint">{{ deferralHint }}</p>

      <!-- running but tunnel list not yet authoritative → neutral, NOT a CTA -->
      <p v-else-if="!playit.tunnelsKnown" class="pb-hint">
        Can't confirm this server's tunnel right now — the playit.gg API isn't
        reachable. This updates automatically.
      </p>

      <!-- running + authoritative + no matching tunnel → actionable -->
      <div v-else-if="!tunnel" class="pb-create">
        <p class="pb-create__text">
          No tunnel forwards to port <code>{{ port }}</code> yet. Create one in your
          playit.gg dashboard with <strong>local port → {{ port }}</strong>.
        </p>
        <a :href="PLAYIT_DASHBOARD_URL" target="_blank" rel="noopener noreferrer" class="pb-link">
          Open playit.gg dashboard ↗
        </a>
      </div>

      <!-- matched tunnel disabled → error for THIS server -->
      <div v-else-if="tunnel.disabled_reason" class="pb-error" role="alert">
        <p class="pb-error__title">This server's tunnel is disabled</p>
        <p class="pb-error__reason">{{ tunnel.disabled_reason }}</p>
      </div>

      <!-- matched + active → connected -->
      <div v-else-if="tunnel.address" class="pb-connected">
        <span class="pb-connected__dot" aria-hidden="true"></span>
        <span class="pb-addr" :title="tunnel.address">{{ tunnel.address }}</span>
        <button
          class="pb-copy"
          :class="{ 'pb-copy--confirmed': copied }"
          type="button"
          :aria-label="copied ? 'Copied!' : 'Copy address'"
          @click="copyAddress"
        >
          <svg v-if="!copied" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="9" y="2" width="6" height="4" rx="1"/>
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </button>
      </div>

      <!-- matched but no address yet (pending setup on playit's side) -->
      <p v-else class="pb-hint">
        Found a tunnel for port {{ port }} — waiting for its public address…
      </p>
    </Panel>

    <ConfirmModal
      :show="confirmConfig !== null"
      :title="confirmConfig?.title || ''"
      :message="confirmConfig?.message || ''"
      :type="confirmConfig?.type || 'warning'"
      :confirm-text="confirmConfig?.confirmText || 'Confirm'"
      :cancel-text="confirmConfig?.cancelText || 'Cancel'"
      @confirm="handleConfirm"
      @cancel="handleConfirmCancel"
    />
  </div>
</template>

<style scoped>
.playit-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

/* ─── Section A ─────────────────────────────────────────────────────────── */
.pa-note {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

/* Header link — deliberately quiet, so it never competes with the primary
   action inside whichever state the panel is showing. */
.pa-dashlink {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.12s ease;
}

.pa-dashlink:hover { color: var(--primary); }
.pa-dashlink:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.pa-scope {
  margin: 0 0 var(--space-3) 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.pa-scope strong {
  color: var(--text-secondary);
  font-weight: 600;
}

.pa-warn {
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--warning) 10%, transparent);
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.pa-onboarding {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  justify-content: space-between;
}

.pa-onboarding__text { flex: 1; min-width: 0; }

.pa-lead {
  margin: 0 0 var(--space-1) 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

.pa-sub {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.pa-error-state {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.pa-error-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--danger) 10%, transparent);
}

.pa-error-banner__icon { flex-shrink: 0; color: var(--danger); margin-top: 1px; }
.pa-error-banner__text { min-width: 0; }

.pa-error-banner__title {
  margin: 0 0 var(--space-1) 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

.pa-error-banner__reason {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  word-wrap: break-word;
}

.pa-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.pa-claiming {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pa-claiming__step {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.pa-claiming__num {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary);
  color: var(--text-on-primary);
  font-size: 11px;
  font-weight: 700;
}

.pa-claiming__link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: 34px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--primary);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--primary) 6%, transparent);
  color: var(--primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  word-break: break-all;
  transition: background 0.12s ease;
}

.pa-claiming__link:hover { background: color-mix(in oklch, var(--primary) 12%, transparent); }
.pa-claiming__link:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.pa-claiming__actions {
  display: flex;
  gap: var(--space-4);
  margin-left: 34px;
}

.pa-textbtn {
  background: transparent;
  border: none;
  padding: 0;
  font: inherit;
  font-size: var(--text-xs);
  color: var(--text-muted);
  cursor: pointer;
  text-decoration: underline;
}

.pa-textbtn:hover { color: var(--text-secondary); }

.pa-active,
.pa-starting {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.pa-active__text,
.pa-starting__text { flex: 1; }

.pa-active__dot,
.pa-starting__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.pa-active__dot { background: var(--success); }

.pa-starting__dot {
  background: var(--warning);
  animation: pa-pulse 1.2s ease-in-out infinite;
}

@keyframes pa-pulse {
  0%, 100% { opacity: 0.5; }
  50%      { opacity: 1; }
}

.pa-active__actions {
  display: flex;
  gap: var(--space-2);
}

.pa-pillbtn {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font: inherit;
  font-size: var(--text-xs);
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.12s ease, border-color 0.12s ease;
}

.pa-pillbtn:hover { color: var(--text-secondary); border-color: var(--text-muted); }

/* ─── Section B ─────────────────────────────────────────────────────────── */
.pb-hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.pb-create__text {
  margin: 0 0 var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.pb-create__text code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}

.pb-link {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  background: var(--primary);
  color: var(--text-on-primary);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
  transition: background 0.15s ease;
}

.pb-link:hover { background: var(--primary-dark); }
.pb-link:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

.pb-error {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--danger) 10%, transparent);
}

.pb-error__title {
  margin: 0 0 var(--space-1) 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.pb-error__reason {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  word-wrap: break-word;
}

.pb-connected {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  width: 100%;
}

.pb-connected__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  flex-shrink: 0;
}

.pb-addr {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pb-copy {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.12s ease, background 0.12s ease, border-color 0.12s ease;
}

.pb-copy:hover {
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.pb-copy:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.pb-copy--confirmed { color: var(--success); }
</style>
