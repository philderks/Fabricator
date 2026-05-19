<script setup>
import { computed, ref } from 'vue'
import Panel from '../ui/Panel.vue'
import AppButton from '../ui/AppButton.vue'
import ConfirmModal from '../modals/ConfirmModal.vue'
import PlayerRow from './PlayerRow.vue'
import { usePlayersStore } from '../../stores/players'
import { useServerStore } from '../../stores/server'

const store = usePlayersStore()
const serverStore = useServerStore()

const nameInput = ref('')
const levelInput = ref(4)
const submitting = ref(false)
const removeTarget = ref(null)

const isRunning = computed(() => serverStore.serverStatus?.status === 'running')

async function submitAdd() {
  const name = nameInput.value.trim()
  // While running, vanilla `op` ignores the level argument — force 4 and let
  // the user know via the disabled level dropdown + hint.
  const level = isRunning.value ? 4 : (Number(levelInput.value) || 4)
  if (!name || submitting.value) return
  submitting.value = true
  try {
    await store.addOp(name, level)
    nameInput.value = ''
    levelInput.value = 4
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

async function changeLevel(op, level) {
  if (isRunning.value) return  // disabled in template; defensive guard
  try { await store.setOpLevel(op.name, Number(level)) } catch (e) { console.error(e) }
}

async function confirmRemove() {
  if (!removeTarget.value) return
  try {
    await store.removeOp(removeTarget.value.name)
  } catch (e) {
    console.error(e)
  } finally {
    removeTarget.value = null
  }
}
</script>

<template>
  <Panel title="Operators">
    <form class="ops-add" @submit.prevent="submitAdd">
      <input v-model="nameInput" class="ops-input" type="text" placeholder="Player name" :disabled="submitting" />
      <select
        v-model="levelInput"
        class="ops-level"
        :disabled="submitting || isRunning"
        :title="isRunning ? 'Stop the server to change op level' : ''"
      >
        <option v-for="l in [1,2,3,4]" :key="l" :value="l">Level {{ l }}</option>
      </select>
      <AppButton type="submit" variant="primary" size="sm" :loading="submitting">+ Add</AppButton>
    </form>
    <p v-if="isRunning" class="ops-hint">
      Op level can only be set while the server is stopped (vanilla `op` ignores level changes at runtime).
    </p>

    <ul v-if="store.ops.length" class="ops-list">
      <PlayerRow
        v-for="p in store.ops"
        :key="p.uuid || p.name"
        :name="p.name"
        :uuid="p.uuid"
        :offline-mode="!store.onlineMode"
        :subtitle="`Level ${p.level || 4}`"
      >
        <template #actions>
          <select
            :value="p.level || 4"
            class="ops-level-inline"
            :disabled="isRunning"
            :title="isRunning ? 'Stop the server to change op level' : ''"
            @change="changeLevel(p, $event.target.value)"
          >
            <option v-for="l in [1,2,3,4]" :key="l" :value="l">L{{ l }}</option>
          </select>
          <AppButton variant="ghost" size="sm" @click="removeTarget = p">Deop</AppButton>
        </template>
      </PlayerRow>
    </ul>
    <div v-else class="ops-empty">No operators.</div>

    <ConfirmModal
      :show="!!removeTarget"
      title="Remove operator?"
      :message="`Remove ${removeTarget?.name} as operator?`"
      type="warning"
      confirm-text="Deop"
      cancel-text="Cancel"
      @confirm="confirmRemove"
      @cancel="removeTarget = null"
    />
  </Panel>
</template>

<style scoped>
.ops-add { display: flex; gap: var(--space-2); margin: var(--space-3) 0 var(--space-2); }
.ops-hint {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-disabled);
}
.ops-input {
  flex: 1; height: 32px; padding: 0 var(--space-3);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-md); color: var(--text-primary);
  font-family: inherit; font-size: var(--text-sm);
}
.ops-input:focus { outline: none; border-color: var(--primary); }
.ops-level, .ops-level-inline {
  height: 32px; padding: 0 var(--space-2);
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius-sm); color: var(--text-primary); font-size: var(--text-xs);
}
.ops-list { list-style: none; margin: 0; padding: 0; }
.ops-empty { padding: var(--space-3) 0; font-size: var(--text-sm); color: var(--text-disabled); }
</style>
