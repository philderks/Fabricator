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
</script>

<template>
  <Panel title="Banned players">
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
  </Panel>
</template>

<style scoped>
.bans-add { display: flex; gap: var(--space-2); margin: var(--space-3) 0 var(--space-2); }
.bans-input {
  height: 32px; padding: 0 var(--space-3);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); color: var(--text-primary);
  font-family: inherit; font-size: var(--text-sm); flex: 1;
}
.bans-input--reason { flex: 2; }
.bans-input:focus { outline: none; border-color: var(--primary); }
.bans-list { list-style: none; margin: 0; padding: 0; }
.bans-empty { padding: var(--space-3) 0; font-size: var(--text-sm); color: var(--text-disabled); }
</style>
