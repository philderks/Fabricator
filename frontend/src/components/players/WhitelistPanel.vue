<script setup>
import { ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ToggleRow from '../ui/ToggleRow.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'
import { useServerStore } from '../../stores/server'

const store = usePlayersStore()
const serverStore = useServerStore()

const nameInput = ref('')
const submitting = ref(false)
const removeTarget = ref(null)

async function submitAdd() {
  const name = nameInput.value.trim()
  if (!name || submitting.value) return
  submitting.value = true
  try {
    await store.addWhitelist(name)
    nameInput.value = ''
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

async function confirmRemove() {
  if (!removeTarget.value) return
  try {
    await store.removeWhitelist(removeTarget.value.name)
  } catch (e) {
    console.error(e)
  } finally {
    removeTarget.value = null
  }
}

async function onToggleActive(value) {
  try {
    await store.toggleWhitelistActive(value)
  } catch (e) {
    console.error(e)
  }
}
</script>

<template>
  <Panel title="Whitelist">
    <div class="whitelist-toggle-row">
      <ToggleRow
        v-if="serverStore.serverStatus?.status === 'running'"
        label="Whitelist active"
        :model-value="store.whitelistActive"
        @update:model-value="onToggleActive"
      />
      <ToggleRow
        v-else
        label="Enforce whitelist"
        :model-value="store.enforceWhitelist"
        :disabled="true"
      />
      <p class="whitelist-toggle-hint">
        <template v-if="serverStore.serverStatus?.status === 'running'">
          Runtime whitelist on/off. Resets to the persisted setting on next start.
        </template>
        <template v-else>
          Persisted setting. Edit in Settings while the server is stopped.
        </template>
      </p>
    </div>

    <form class="whitelist-add" @submit.prevent="submitAdd">
      <input
        v-model="nameInput"
        class="whitelist-input"
        type="text"
        placeholder="Player name"
        :disabled="submitting"
      />
      <AppButton type="submit" variant="primary" size="sm" :loading="submitting">+ Add</AppButton>
    </form>

    <ul v-if="store.whitelist.length" class="whitelist-list">
      <PlayerRow
        v-for="p in store.whitelist"
        :key="p.uuid || p.name"
        :name="p.name"
        :uuid="p.uuid"
        :offline-mode="!store.onlineMode"
        :subtitle="p.uuid || ''"
      >
        <template #actions>
          <AppButton variant="ghost" size="sm" @click="removeTarget = p">Remove</AppButton>
        </template>
      </PlayerRow>
    </ul>
    <div v-else class="whitelist-empty">No players whitelisted yet.</div>

    <ConfirmModal
      :show="!!removeTarget"
      title="Remove from whitelist?"
      :message="`Remove ${removeTarget?.name} from the whitelist?`"
      type="warning"
      confirm-text="Remove"
      cancel-text="Cancel"
      @confirm="confirmRemove"
      @cancel="removeTarget = null"
    />
  </Panel>
</template>

<style scoped>
.whitelist-toggle-row { display: flex; flex-direction: column; gap: 4px; }
.whitelist-toggle-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-disabled);
}
.whitelist-add {
  display: flex;
  gap: var(--space-2);
  margin: var(--space-3) 0 var(--space-2);
}
.whitelist-input {
  flex: 1;
  height: 32px;
  padding: 0 var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--text-sm);
}
.whitelist-input:focus { outline: none; border-color: var(--primary); }
.whitelist-list { list-style: none; margin: 0; padding: 0; }
.whitelist-empty {
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--text-disabled);
}
</style>
