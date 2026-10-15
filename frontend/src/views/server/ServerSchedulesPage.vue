<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import ToggleRow from '../../components/ui/ToggleRow.vue'
import ConfirmModal from '../../components/modals/ConfirmModal.vue'
import ScheduleEditorModal from '../../components/schedules/ScheduleEditorModal.vue'
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  runSchedule,
  updateSchedule
} from '../../api/schedules'
import { useServerStore } from '../../stores/server'
import { useToast } from '../../composables/useToast'
import { formatTimestamp } from '../../utils/format'
import { formatList, t } from '../../i18n'

const serverStore = useServerStore()
const toast = useToast()

const schedules = ref([])
// False until the current server's list first arrives: drives the empty state,
// and keeps background refreshes from toasting the same error every poll.
const loaded = ref(false)
const REFRESH_MS = 15000
let refreshTimer = null

// Editor: `editorOpen` + the schedule being edited (null = new).
const editorOpen = ref(false)
const editing = ref(null)
const saving = ref(false)
const editorError = ref(null)

const toDelete = ref(null)
const deleting = ref(false)

async function load() {
  const serverId = serverStore.currentServerId
  if (!serverId) return
  try {
    const list = await listSchedules(serverId)
    // Drop a reply that lands after the user switched servers.
    if (serverId !== serverStore.currentServerId) return
    schedules.value = list
    loaded.value = true
  } catch (err) {
    if (!loaded.value) toast.error(err?.message || t('schedules.loadFailed'), t('nav.schedules'))
  }
}

function openEditor(schedule = null) {
  editing.value = schedule
  editorError.value = null
  editorOpen.value = true
}

async function save(payload) {
  saving.value = true
  editorError.value = null
  try {
    const serverId = serverStore.currentServerId
    if (editing.value) await updateSchedule(serverId, editing.value.id, payload)
    else await createSchedule(serverId, payload)
    toast.success(t('schedules.saved'), t('nav.schedules'))
    editorOpen.value = false
    await load()
  } catch (err) {
    editorError.value = err?.message || t('schedules.saveFailed')
  } finally {
    saving.value = false
  }
}

// The list annotations aren't part of the schedule body the API accepts.
function bodyOf({ id, nextRunTime, lastRun, ...body }) {
  return body
}

async function setEnabled(schedule, enabled) {
  // Flip the prop first: ToggleRow binds :checked, so only a prop change can
  // move the switch back if the save fails.
  schedule.enabled = enabled
  try {
    await updateSchedule(serverStore.currentServerId, schedule.id, bodyOf(schedule))
    await load()
  } catch (err) {
    schedule.enabled = !enabled
    toast.error(err?.message || t('schedules.saveFailed'), t('nav.schedules'))
  }
}

async function runNow(schedule) {
  try {
    await runSchedule(serverStore.currentServerId, schedule.id)
    toast.info(t('schedules.started', { name: schedule.name }), t('nav.schedules'))
    // Steps without waits finish almost at once; pick up their lastRun.
    setTimeout(load, 2000)
  } catch (err) {
    toast.error(err?.message || t('schedules.runFailed'), t('nav.schedules'))
  }
}

async function confirmDelete() {
  deleting.value = true
  try {
    await deleteSchedule(serverStore.currentServerId, toDelete.value.id)
    toast.success(t('schedules.deleted'), t('nav.schedules'))
    toDelete.value = null
    await load()
  } catch (err) {
    toast.error(err?.message || t('schedules.deleteFailed'), t('nav.schedules'))
  } finally {
    deleting.value = false
  }
}

function describeTrigger(trigger) {
  if (trigger.type === 'interval') return t('schedules.summary.interval', trigger.minutes)
  if (trigger.type === 'daily') {
    const days = trigger.days.length
      ? formatList(trigger.days.map(day => t(`schedules.days.${day}`)))
      : t('schedules.summary.everyDay')
    return t('schedules.summary.daily', { time: trigger.time, days })
  }
  return t('schedules.summary.cron', { expression: trigger.expression })
}

function formatDelay(seconds) {
  return seconds % 60 === 0 ? `${seconds / 60}m` : `${seconds}s`
}

watch(
  () => serverStore.currentServerId,
  (id, oldId) => {
    if (!id || id === oldId) return
    schedules.value = []
    loaded.value = false
    load()
  }
)

// Keeps nextRunTime and lastRun current (runs with waits finish much later).
onMounted(() => {
  load()
  refreshTimer = setInterval(load, REFRESH_MS)
})

onUnmounted(() => clearInterval(refreshTimer))
</script>

<template>
  <div class="schedules-page">
    <header class="schedules-page__toolbar">
      <div class="schedules-page__title-block">
        <h2 class="schedules-page__title">{{ $t('nav.schedules') }}</h2>
        <p class="schedules-page__sub">{{ $t('schedules.subtitle') }}</p>
      </div>
      <AppButton variant="primary" size="md" @click="openEditor()">{{ $t('schedules.new') }}</AppButton>
    </header>

    <p v-if="loaded && !schedules.length" class="schedules-page__empty">{{ $t('schedules.empty') }}</p>

    <Panel v-for="schedule in schedules" :key="schedule.id" :title="schedule.name">
      <template #action>
        <div class="schedules-page__actions">
          <AppButton variant="ghost" size="sm" @click="runNow(schedule)">{{ $t('schedules.runNow') }}</AppButton>
          <AppButton variant="ghost" size="sm" @click="openEditor(schedule)">{{ $t('schedules.edit') }}</AppButton>
          <AppButton variant="danger" size="sm" @click="toDelete = schedule">{{ $t('common.delete') }}</AppButton>
        </div>
      </template>

      <div class="schedule-card">
        <dl class="schedule-card__meta">
          <div>
            <dt>{{ $t('schedules.when') }}</dt>
            <dd>{{ describeTrigger(schedule.trigger) }}</dd>
          </div>
          <div>
            <dt>{{ $t('schedules.nextRun') }}</dt>
            <dd>{{ schedule.nextRunTime ? formatTimestamp(schedule.nextRunTime) : '—' }}</dd>
          </div>
          <div>
            <dt>{{ $t('schedules.lastRun') }}</dt>
            <dd v-if="schedule.lastRun" :title="schedule.lastRun.message">
              <span :class="`schedule-card__status schedule-card__status--${schedule.lastRun.status}`">
                {{ $t(`schedules.status.${schedule.lastRun.status}`) }}
              </span>
              · {{ formatTimestamp(schedule.lastRun.at) }}
            </dd>
            <dd v-else>—</dd>
          </div>
        </dl>

        <ol class="schedule-card__steps">
          <li v-for="(step, i) in schedule.steps" :key="i">
            <span v-if="step.delaySeconds" class="schedule-card__wait">
              {{ $t('schedules.summary.wait', { delay: formatDelay(step.delaySeconds) }) }}
            </span>
            <code v-if="step.action === 'command'">{{ step.command }}</code>
            <strong v-else>{{ $t(`schedules.actions.${step.action}`) }}</strong>
          </li>
        </ol>

        <ToggleRow
          :model-value="schedule.enabled"
          :label="$t('schedules.fields.enabled')"
          @update:model-value="value => setEnabled(schedule, value)"
        />
      </div>
    </Panel>

    <ScheduleEditorModal
      :show="editorOpen"
      :schedule="editing"
      :saving="saving"
      :error="editorError"
      @save="save"
      @cancel="editorOpen = false"
    />

    <ConfirmModal
      :show="!!toDelete"
      type="danger"
      :title="$t('schedules.deleteTitle')"
      :message="$t('schedules.deleteMessage', { name: toDelete?.name })"
      :confirm-text="$t('common.delete')"
      :loading="deleting"
      @confirm="confirmDelete"
      @cancel="toDelete = null"
    />
  </div>
</template>

<style scoped>
.schedules-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  max-width: 100%;
}

.schedules-page__toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.schedules-page__title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.schedules-page__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.schedules-page__sub,
.schedules-page__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.schedules-page__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.schedule-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.schedule-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  margin: 0;
}

.schedule-card__meta dt {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.schedule-card__meta dd {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.schedule-card__status--ok {
  color: var(--success);
}

.schedule-card__status--skipped {
  color: var(--warning);
}

.schedule-card__status--error {
  color: var(--danger);
}

.schedule-card__steps {
  margin: 0;
  padding-left: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.schedule-card__steps code {
  font-family: var(--font-mono);
  word-break: break-all;
}

.schedule-card__wait {
  color: var(--text-muted);
  margin-right: var(--space-2);
}
</style>
