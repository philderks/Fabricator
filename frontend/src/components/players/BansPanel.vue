<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'
import { useToast } from '../../composables/useToast'

const store = usePlayersStore()
const toast = useToast()

// ── Tab state ──────────────────────────────────────────────────────────────
const activeSection = ref('players') // 'players' | 'ips'

// ── Player bans ────────────────────────────────────────────────────────────
const nameInput = ref('')
const reasonInput = ref('')
const submitting = ref(false)
const removeTarget = ref(null)

async function submitAdd() {
  const name = nameInput.value.trim()
  if (!name || submitting.value) return
  submitting.value = true
  try {
    await store.addBan(name, reasonInput.value.trim() || null)
    nameInput.value = ''
    reasonInput.value = ''
  } catch (e) {
    toast.error(e.message || 'Failed to ban player', 'Bans')
  } finally {
    submitting.value = false
  }
}

async function confirmUnban() {
  if (!removeTarget.value) return
  try {
    await store.removeBan(removeTarget.value.name)
  } catch (e) {
    toast.error(e.message || 'Failed to unban player', 'Bans')
  } finally {
    removeTarget.value = null
  }
}

function subtitle(p) {
  const parts = []
  if (p.reason) parts.push(p.reason)
  if (p.created) parts.push(`banned ${String(p.created).split(' ')[0]}`)
  return parts.join(' · ')
}

// ── IP bans ────────────────────────────────────────────────────────────────
const ipInput = ref('')
const ipReasonInput = ref('')
const ipSubmitting = ref(false)
const ipRemoveTarget = ref(null)

async function submitIpBan() {
  const ip = ipInput.value.trim()
  if (!ip || ipSubmitting.value) return
  ipSubmitting.value = true
  try {
    await store.addIpBan(ip, ipReasonInput.value.trim() || null)
    ipInput.value = ''
    ipReasonInput.value = ''
  } catch (e) {
    toast.error(e.message || 'Failed to ban IP', 'IP Bans')
  } finally {
    ipSubmitting.value = false
  }
}

async function confirmIpUnban() {
  if (!ipRemoveTarget.value) return
  try {
    await store.removeIpBan(ipRemoveTarget.value.ip)
  } catch (e) {
    toast.error(e.message || 'Failed to unban IP', 'IP Bans')
  } finally {
    ipRemoveTarget.value = null
  }
}

function ipSubtitle(entry) {
  const parts = []
  if (entry.reason && entry.reason !== 'Banned by an operator.') parts.push(entry.reason)
  if (entry.created) parts.push(`banned ${String(entry.created).split(' ')[0]}`)
  return parts.join(' · ')
}
</script>

<template>
  <Panel title="Banned">
    <!-- Section toggle -->
    <div class="bans-section-tabs" role="tablist">
      <button
        v-for="s in [{ id: 'players', label: `Players (${store.bans.length})` }, { id: 'ips', label: `IPs (${store.ipBans.length})` }]"
        :key="s.id"
        :class="['bans-section-tab', { 'bans-section-tab--active': activeSection === s.id }]"
        role="tab"
        :aria-selected="activeSection === s.id"
        type="button"
        @click="activeSection = s.id"
      >{{ s.label }}</button>
    </div>

    <!-- Player bans section -->
    <template v-if="activeSection === 'players'">
      <form class="bans-add" @submit.prevent="submitAdd">
        <input v-model="nameInput" class="bans-input" type="text" placeholder="Player name" :disabled="submitting" />
        <input v-model="reasonInput" class="bans-input bans-input--reason" type="text" placeholder="Reason (optional)" :disabled="submitting" />
        <AppButton type="submit" variant="danger" size="sm" :loading="submitting">+ Ban</AppButton>
      </form>

      <ul v-if="store.bans.length" class="bans-list">
        <PlayerRow
          v-for="p in store.bans"
          :key="p.uuid || p.name"
          :name="p.name"
          :uuid="p.uuid"
          :offline-mode="!store.onlineMode"
          :subtitle="subtitle(p)"
        >
          <template #actions>
            <AppButton variant="ghost" size="sm" @click="removeTarget = p">Unban</AppButton>
          </template>
        </PlayerRow>
      </ul>
      <div v-else class="bans-empty">No banned players.</div>

      <ConfirmModal
        :show="!!removeTarget"
        title="Unban player?"
        :message="`Unban ${removeTarget?.name}?`"
        type="warning"
        confirm-text="Unban"
        cancel-text="Cancel"
        @confirm="confirmUnban"
        @cancel="removeTarget = null"
      />
    </template>

    <!-- IP bans section -->
    <template v-else>
      <form class="bans-add" @submit.prevent="submitIpBan">
        <input v-model="ipInput" class="bans-input" type="text" placeholder="IP or wildcard (e.g. 192.168.*)" :disabled="ipSubmitting" />
        <input v-model="ipReasonInput" class="bans-input bans-input--reason" type="text" placeholder="Reason (optional)" :disabled="ipSubmitting" />
        <AppButton type="submit" variant="danger" size="sm" :loading="ipSubmitting">+ Ban IP</AppButton>
      </form>

      <ul v-if="store.ipBans.length" class="bans-list">
        <li v-for="entry in store.ipBans" :key="entry.ip" class="ip-ban-row">
          <div class="ip-ban-row__main">
            <span class="ip-ban-row__ip">{{ entry.ip }}</span>
            <span v-if="ipSubtitle(entry)" class="ip-ban-row__sub">{{ ipSubtitle(entry) }}</span>
          </div>
          <AppButton variant="ghost" size="sm" @click="ipRemoveTarget = entry">Unban</AppButton>
        </li>
      </ul>
      <div v-else class="bans-empty">No banned IPs.</div>

      <ConfirmModal
        :show="!!ipRemoveTarget"
        title="Unban IP?"
        :message="`Unban ${ipRemoveTarget?.ip}?`"
        type="warning"
        confirm-text="Unban"
        cancel-text="Cancel"
        @confirm="confirmIpUnban"
        @cancel="ipRemoveTarget = null"
      />
    </template>
  </Panel>
</template>

<style scoped>
/* ── Section tabs ── */
.bans-section-tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-color);
}

.bans-section-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  padding: var(--space-1) var(--space-2);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.bans-section-tab:hover { color: var(--text-secondary); }
.bans-section-tab--active { color: var(--danger); border-bottom-color: var(--danger); }

/* ── Shared form ── */
.bans-add { display: flex; gap: var(--space-2); margin: 0 0 var(--space-2); }
.bans-input {
  height: 32px; padding: 0 var(--space-3);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); color: var(--text-primary);
  font-family: inherit; font-size: var(--text-sm); flex: 1;
}
.bans-input--reason { flex: 2; }
.bans-input:focus { outline: none; border-color: var(--danger); }
.bans-list { list-style: none; margin: 0; padding: 0; }
.bans-empty { padding: var(--space-3) 0; font-size: var(--text-sm); color: var(--text-disabled); }

/* ── IP ban row ── */
.ip-ban-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-color);
}
.ip-ban-row:last-child { border-bottom: none; }
.ip-ban-row__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.ip-ban-row__ip { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); font-family: var(--font-mono); }
.ip-ban-row__sub { font-size: var(--text-xs); color: var(--text-disabled); }
</style>
