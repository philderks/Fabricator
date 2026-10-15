<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import { usePlayersStore } from '../../stores/players'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

const store = usePlayersStore()
const toast = useToast()

const expanded = ref(false)
const ipInput = ref('')
const ipReasonInput = ref('')
const submitting = ref(false)
const removeTarget = ref(null)

async function submitIpBan() {
  const ip = ipInput.value.trim()
  if (!ip || submitting.value) return
  submitting.value = true
  try {
    await store.addIpBan(ip, ipReasonInput.value.trim() || null)
    ipInput.value = ''
    ipReasonInput.value = ''
  } catch (e) {
    toast.error(e.message || t('players.ipBans.banFailed'), t('players.ipBans.toastTitle'))
  } finally {
    submitting.value = false
  }
}

async function confirmUnban() {
  if (!removeTarget.value) return
  try {
    await store.removeIpBan(removeTarget.value.ip)
  } catch (e) {
    toast.error(e.message || t('players.ipBans.unbanFailed'), t('players.ipBans.toastTitle'))
  } finally {
    removeTarget.value = null
  }
}

function subtitle(entry) {
  const parts = []
  if (entry.reason && entry.reason !== 'Banned by an operator.') parts.push(entry.reason)
  if (entry.created) parts.push(t('players.ipBans.bannedOn', { date: String(entry.created).split(' ')[0] }))
  return parts.join(' · ')
}
</script>

<template>
  <Panel :title="$t('players.ipBans.title', { n: store.ipBans.length })">
    <template #action>
      <button class="ipban-toggle" type="button" @click="expanded = !expanded">
        {{ expanded ? $t('common.collapse') : $t('common.manage') }}
      </button>
    </template>

    <div v-if="expanded">
      <form class="ipban-add" @submit.prevent="submitIpBan">
        <input v-model="ipInput" class="ipban-input" type="text" :placeholder="$t('players.ipBans.ipPlaceholder')" :disabled="submitting" />
        <input v-model="ipReasonInput" class="ipban-input ipban-input--reason" type="text" :placeholder="$t('players.ipBans.reasonPlaceholder')" :disabled="submitting" />
        <AppButton type="submit" variant="danger" size="sm" :loading="submitting">{{ $t('players.ipBans.banIp') }}</AppButton>
      </form>

      <ul v-if="store.ipBans.length" class="ipban-list">
        <li v-for="entry in store.ipBans" :key="entry.ip" class="ipban-row">
          <div class="ipban-row__main">
            <span class="ipban-row__ip">{{ entry.ip }}</span>
            <span v-if="subtitle(entry)" class="ipban-row__sub">{{ subtitle(entry) }}</span>
          </div>
          <AppButton variant="ghost" size="sm" @click="removeTarget = entry">{{ $t('players.unban') }}</AppButton>
        </li>
      </ul>
      <div v-else class="ipban-empty">{{ $t('players.ipBans.empty') }}</div>
    </div>

    <ConfirmModal
      :show="!!removeTarget"
      :title="$t('players.ipBans.unbanTitle')"
      :message="$t('players.ipBans.unbanMessage', { ip: removeTarget?.ip })"
      type="warning"
      :confirm-text="$t('players.unban')"
      @confirm="confirmUnban"
      @cancel="removeTarget = null"
    />
  </Panel>
</template>

<style scoped>
.ipban-toggle {
  background: none; border: none;
  font-size: var(--text-xs); color: var(--primary);
  cursor: pointer; padding: 0;
}
.ipban-toggle:hover { text-decoration: underline; }
.ipban-add { display: flex; gap: var(--space-2); margin: 0 0 var(--space-2); }
.ipban-input {
  height: 32px; padding: 0 var(--space-3);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); color: var(--text-primary);
  font-family: inherit; font-size: var(--text-sm); flex: 1;
}
.ipban-input--reason { flex: 2; }
.ipban-input:focus { outline: none; border-color: var(--danger); }
.ipban-list { list-style: none; margin: 0; padding: 0; }
.ipban-empty { padding: var(--space-3) 0; font-size: var(--text-sm); color: var(--text-disabled); }
.ipban-row {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) 0; border-bottom: 1px solid var(--border-color);
}
.ipban-row:last-child { border-bottom: none; }
.ipban-row__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.ipban-row__ip { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); font-family: var(--font-mono); }
.ipban-row__sub { font-size: var(--text-xs); color: var(--text-disabled); }
</style>
