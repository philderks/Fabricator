<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/useToast'
import { copyToClipboard } from '../utils/clipboard'
import Panel from '../components/ui/Panel.vue'
import FormField from '../components/ui/FormField.vue'
import ToggleRow from '../components/ui/ToggleRow.vue'
import AppButton from '../components/ui/AppButton.vue'
import ConfirmModal from '../components/modals/ConfirmModal.vue'
import { getMcp, setMcpEnabled, createMcpToken, deleteMcpToken } from '../api/mcp'
import { buildMcpClientConfig } from '../config/mcpClientConfig'

const auth = useAuthStore()
const toast = useToast()

const enabled = ref(false)
const tokens = ref([])

const form = ref({ name: '', scope: 'read' })
const creating = ref(false)
const createError = ref('')

const newToken = ref('') // the one-time secret, held only in memory
const copied = ref(false)
let copyTimer = null

const panelUrl = ref(window.location.origin)

const toggling = ref(false)
const revokeTarget = ref(null)
const revoking = ref(false)

const configJson = computed(() =>
  JSON.stringify(
    buildMcpClientConfig({ url: panelUrl.value, token: newToken.value || undefined }),
    null,
    2
  )
)

async function load() {
  try {
    const data = await getMcp()
    enabled.value = Boolean(data.enabled)
    tokens.value = Array.isArray(data.tokens) ? data.tokens : []
  } catch (err) {
    toast.error(err?.message || 'Could not load MCP settings', 'MCP')
  }
}

async function onToggle(next) {
  toggling.value = true
  try {
    await setMcpEnabled(next)
    enabled.value = next
  } catch (err) {
    toast.error(err?.message || 'Could not change the switch', 'MCP')
    // enabled is left unchanged; the toggle reflects :model-value.
  } finally {
    toggling.value = false
  }
}

async function onCreate() {
  createError.value = ''
  creating.value = true
  try {
    const created = await createMcpToken(form.value.name, form.value.scope)
    newToken.value = created.token
    copied.value = false
    form.value = { name: '', scope: 'read' }
    await load()
  } catch (err) {
    createError.value = err?.message || 'Could not create the token'
  } finally {
    creating.value = false
  }
}

async function copySecret() {
  if (!(await copyToClipboard(newToken.value))) return
  copied.value = true
  toast.success('Token copied', 'MCP')
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
    copyTimer = null
  }, 2000)
}

function askRevoke(token) {
  revokeTarget.value = token
}

async function confirmRevoke() {
  if (!revokeTarget.value) return
  revoking.value = true
  try {
    await deleteMcpToken(revokeTarget.value.id)
    revokeTarget.value = null
    await load()
  } catch (err) {
    toast.error(err?.message || 'Could not revoke the token', 'MCP')
  } finally {
    revoking.value = false
  }
}

function cancelRevoke() {
  if (revoking.value) return
  revokeTarget.value = null
}

function scopeLabel(scope) {
  return scope === 'manage' ? 'Read and manage' : 'Read only'
}

function shortDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function relativeTime(iso) {
  if (!iso) return 'Never used'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'Never used'
  const diffMs = then - Date.now()
  const mins = Math.round(diffMs / 60000)
  if (Math.abs(mins) < 1) return 'Just now'
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (Math.abs(mins) < 60) return rtf.format(mins, 'minute')
  const hours = Math.round(diffMs / 3600000)
  if (Math.abs(hours) < 24) return rtf.format(hours, 'hour')
  return rtf.format(Math.round(diffMs / 86400000), 'day')
}

onMounted(() => {
  // Managed mode: the whole section is hidden; skip the API call entirely.
  if (auth.managed) return
  load()
})
</script>

<template>
  <div v-if="!auth.managed" class="mcp-page">
    <header class="mcp-page__head">
      <h1 class="mcp-page__title">Model Context Protocol</h1>
      <p class="mcp-page__intro">
        Connect an AI assistant to this panel. It can read your server's status,
        logs and installed mods — and, with a manage token, start and stop the
        server or change mods.
      </p>
    </header>

    <Panel title="Access">
      <ToggleRow
        :model-value="enabled"
        label="Enable MCP access"
        :disabled="toggling"
        @update:model-value="onToggle"
      />
      <p v-if="!enabled" class="mcp-note">
        MCP access is off. Existing tokens stay saved but are rejected until you
        turn this back on.
      </p>
    </Panel>

    <Panel title="Tokens">
      <form class="mcp-create" @submit.prevent="onCreate">
        <FormField label="Name" hint="So you can tell your tokens apart later." v-slot="{ id, describedBy }">
          <input
            :id="id"
            :aria-describedby="describedBy"
            v-model="form.name"
            type="text"
            class="mcp-input"
            autocomplete="off"
          />
        </FormField>

        <fieldset class="mcp-scope">
          <legend class="mcp-scope__legend">Access</legend>
          <label class="mcp-scope__option" :class="{ 'is-active': form.scope === 'read' }">
            <input type="radio" value="read" v-model="form.scope" />
            <span>Read only — server status, logs, installed mods.</span>
          </label>
          <label class="mcp-scope__option" :class="{ 'is-active': form.scope === 'manage' }">
            <input type="radio" value="manage" v-model="form.scope" />
            <span>Read and manage — also start, stop and restart the server, install it, and add or remove mods.</span>
          </label>
        </fieldset>

        <p class="mcp-warn">
          Logs contain text written by mods and players. An assistant with a
          manage token can act on what it reads there.
        </p>

        <div class="mcp-create__actions">
          <AppButton type="submit" :loading="creating">Create token</AppButton>
        </div>
        <p v-if="createError" class="mcp-error">{{ createError }}</p>
      </form>

      <div v-if="newToken" class="mcp-secret">
        <h4 class="mcp-secret__title">Your new token</h4>
        <p class="mcp-secret__body">
          Copy it now. It is not stored in readable form and cannot be shown again.
        </p>
        <div class="mcp-secret__row">
          <code class="mcp-code">{{ newToken }}</code>
          <AppButton size="sm" variant="ghost" @click="copySecret">
            {{ copied ? 'Copied' : 'Copy' }}
          </AppButton>
        </div>
      </div>

      <p v-if="!tokens.length" class="mcp-note">No tokens yet. Create one to connect a client.</p>
      <div v-else class="mcp-table-wrap">
        <table class="mcp-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Access</th>
              <th>Created</th>
              <th>Last used</th>
              <th class="mcp-table__actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tokens" :key="t.id">
              <td>{{ t.name }}</td>
              <td>{{ scopeLabel(t.scope) }}</td>
              <td>{{ shortDate(t.created_at) }}</td>
              <td>{{ relativeTime(t.last_used_at) }}</td>
              <td class="mcp-table__actions">
                <AppButton size="sm" variant="danger" @click="askRevoke(t)">Revoke</AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <Panel title="Connect a client">
      <FormField
        label="Panel URL"
        hint="The address your client can reach this panel at. Change it if the client runs on a different machine."
        v-slot="{ id, describedBy }"
      >
        <input :id="id" :aria-describedby="describedBy" v-model="panelUrl" type="text" class="mcp-input" />
      </FormField>

      <p class="mcp-config-intro">Add this to your MCP client's configuration.</p>
      <pre class="mcp-config">{{ configJson }}</pre>
      <p class="mcp-warn">
        The token is stored in plain text in that file — treat it like a password.
      </p>
    </Panel>

    <ConfirmModal
      :show="Boolean(revokeTarget)"
      title="Revoke token"
      message="Revoke this token? Any client using it stops working immediately."
      type="danger"
      confirm-text="Revoke"
      cancel-text="Cancel"
      :loading="revoking"
      @confirm="confirmRevoke"
      @cancel="cancelRevoke"
    />
  </div>
</template>

<style scoped>
.mcp-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 880px;
  padding: var(--space-4);
}

.mcp-page__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-page__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.mcp-page__intro {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
  max-width: 60ch;
}

.mcp-note {
  margin: var(--space-2) 0 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.mcp-create {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.mcp-input {
  width: 100%;
  padding: 7px var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
}

.mcp-input:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 1px;
}

.mcp-scope {
  border: 0;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-scope__legend {
  padding: 0;
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.mcp-scope__option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  transition: border-color 120ms ease, background 120ms ease;
}

.mcp-scope__option:hover {
  border-color: var(--text-muted);
}

.mcp-scope__option.is-active {
  border-color: var(--primary);
  background: color-mix(in oklch, var(--primary) 8%, transparent);
}

.mcp-scope__option input[type='radio'] {
  margin-top: 2px;
  width: 16px;
  height: 16px;
  accent-color: var(--primary);
  cursor: pointer;
  flex-shrink: 0;
}

.mcp-warn {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--warning);
  line-height: var(--leading-normal);
}

.mcp-error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--danger);
}

.mcp-create__actions {
  display: flex;
}

.mcp-secret {
  margin-top: var(--space-4);
  padding: var(--space-3);
  border: 1px solid var(--primary);
  border-radius: var(--radius-sm);
  background: color-mix(in oklch, var(--primary) 6%, transparent);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-secret__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.mcp-secret__body {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.mcp-secret__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.mcp-code {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  white-space: nowrap;
  padding: 6px var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--text-xs);
  color: var(--text-primary);
}

.mcp-table-wrap {
  margin-top: var(--space-4);
  overflow-x: auto;
}

.mcp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.mcp-table th {
  text-align: left;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-color);
}

.mcp-table td {
  padding: var(--space-2) var(--space-3);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}

.mcp-table__actions {
  text-align: right;
  width: 1%;
  white-space: nowrap;
}

.mcp-config-intro {
  margin: var(--space-3) 0 var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.mcp-config {
  margin: 0 0 var(--space-2);
  padding: var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--text-xs);
  color: var(--text-primary);
  line-height: var(--leading-normal);
  overflow-x: auto;
}
</style>
