<script setup>
import { ref, watch } from 'vue'
import BaseModal from '../modals/BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import ToggleRow from '../ui/ToggleRow.vue'
import { browserTimeZone } from '../../stores/backups'

const props = defineProps({
  show: { type: Boolean, required: true },
  // The schedule being edited, or null for a new one.
  schedule: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  error: { type: String, default: null }
})

const emit = defineEmits(['save', 'cancel'])

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const ACTIONS = ['command', 'start', 'stop', 'restart']
const MAX_STEPS = 20

const timeZone = browserTimeZone()

const newStep = () => ({ action: 'command', command: '', delaySeconds: 0 })

// The form keeps every trigger's fields so switching type doesn't lose input;
// toPayload() sends only the selected one.
const blankDraft = () => ({
  name: '',
  enabled: true,
  triggerType: 'daily',
  minutes: 30,
  time: '04:00',
  days: [],
  expression: '0 4 * * *',
  steps: [newStep()]
})

function draftFrom(schedule) {
  const trigger = schedule.trigger
  return {
    ...blankDraft(),
    name: schedule.name,
    enabled: schedule.enabled,
    triggerType: trigger.type,
    ...(trigger.type === 'interval' && { minutes: trigger.minutes }),
    ...(trigger.type === 'daily' && { time: trigger.time, days: [...trigger.days] }),
    ...(trigger.type === 'cron' && { expression: trigger.expression }),
    steps: schedule.steps.map(step => ({ ...newStep(), ...step }))
  }
}

const draft = ref(blankDraft())

watch(
  () => props.show,
  (open) => {
    if (open) draft.value = props.schedule ? draftFrom(props.schedule) : blankDraft()
  }
)

function moveStep(index, offset) {
  const steps = draft.value.steps
  ;[steps[index], steps[index + offset]] = [steps[index + offset], steps[index]]
}

function toPayload() {
  const d = draft.value
  const trigger = {
    interval: { type: 'interval', minutes: d.minutes },
    daily: { type: 'daily', time: d.time, days: d.days },
    cron: { type: 'cron', expression: d.expression.trim() }
  }[d.triggerType]
  return {
    name: d.name.trim(),
    enabled: d.enabled,
    timezone: timeZone,
    trigger,
    steps: d.steps.map(({ action, command, delaySeconds }) =>
      action === 'command' ? { action, command, delaySeconds } : { action, delaySeconds }
    )
  }
}
</script>

<template>
  <BaseModal
    :show="props.show"
    :title="props.schedule ? $t('schedules.editTitle') : $t('schedules.newTitle')"
    size="large"
    :close-on-escape="!props.saving"
    @close="emit('cancel')"
  >
    <div class="schedule-editor">
      <FormField :label="$t('schedules.fields.name')">
        <template #default="{ id }">
          <input
            :id="id"
            v-model="draft.name"
            type="text"
            maxlength="100"
            class="schedule-editor__input"
            :placeholder="$t('schedules.fields.namePlaceholder')"
          />
        </template>
      </FormField>

      <FormField
        :label="$t('schedules.fields.when')"
        :hint="timeZone ? $t('schedules.fields.timeZoneHint', { zone: timeZone }) : ''"
      >
        <template #default="{ id, describedBy }">
          <select :id="id" v-model="draft.triggerType" class="schedule-editor__input" :aria-describedby="describedBy">
            <option value="interval">{{ $t('schedules.trigger.interval') }}</option>
            <option value="daily">{{ $t('schedules.trigger.daily') }}</option>
            <option value="cron">{{ $t('schedules.trigger.cron') }}</option>
          </select>
        </template>
      </FormField>

      <FormField v-if="draft.triggerType === 'interval'" :label="$t('schedules.fields.minutes')">
        <template #default="{ id }">
          <input :id="id" v-model.number="draft.minutes" type="number" min="1" max="10080" class="schedule-editor__input schedule-editor__input--short" />
        </template>
      </FormField>

      <template v-else-if="draft.triggerType === 'daily'">
        <FormField :label="$t('schedules.fields.time')">
          <template #default="{ id }">
            <input :id="id" v-model="draft.time" type="time" class="schedule-editor__input schedule-editor__input--short" />
          </template>
        </FormField>
        <fieldset class="schedule-editor__fieldset">
          <legend class="schedule-editor__legend">{{ $t('schedules.fields.days') }}</legend>
          <div class="schedule-editor__days">
            <label v-for="day in DAYS" :key="day" class="schedule-editor__day">
              <input v-model="draft.days" type="checkbox" :value="day" />
              {{ $t(`schedules.days.${day}`) }}
            </label>
          </div>
          <p class="schedule-editor__hint">{{ $t('schedules.fields.daysHint') }}</p>
        </fieldset>
      </template>

      <FormField v-else :label="$t('schedules.fields.cron')" :hint="$t('schedules.fields.cronHint')">
        <template #default="{ id, describedBy }">
          <input
            :id="id"
            v-model="draft.expression"
            type="text"
            class="schedule-editor__input schedule-editor__input--mono"
            placeholder="0 4 * * mon-fri"
            :aria-describedby="describedBy"
          />
        </template>
      </FormField>

      <fieldset class="schedule-editor__fieldset">
        <legend class="schedule-editor__legend">{{ $t('schedules.fields.steps') }}</legend>
        <p class="schedule-editor__hint">{{ $t('schedules.fields.stepsHint') }}</p>
        <div class="schedule-editor__step schedule-editor__step--head" aria-hidden="true">
          <span>{{ $t('schedules.fields.wait') }}</span>
          <span>{{ $t('schedules.fields.action') }}</span>
          <span>{{ $t('schedules.fields.command') }}</span>
        </div>
        <div v-for="(step, i) in draft.steps" :key="i" class="schedule-editor__step">
          <input
            v-model.number="step.delaySeconds"
            type="number"
            min="0"
            max="3600"
            class="schedule-editor__input"
            :aria-label="$t('schedules.fields.wait')"
          />
          <select v-model="step.action" class="schedule-editor__input" :aria-label="$t('schedules.fields.action')">
            <option v-for="action in ACTIONS" :key="action" :value="action">{{ $t(`schedules.actions.${action}`) }}</option>
          </select>
          <input
            v-if="step.action === 'command'"
            v-model="step.command"
            type="text"
            maxlength="1000"
            class="schedule-editor__input schedule-editor__input--mono"
            :placeholder="$t('schedules.fields.commandPlaceholder')"
            :aria-label="$t('schedules.fields.command')"
          />
          <span v-else></span>
          <div class="schedule-editor__step-actions">
            <AppButton variant="ghost" size="sm" :disabled="i === 0" :aria-label="$t('schedules.moveUp')" @click="moveStep(i, -1)">↑</AppButton>
            <AppButton variant="ghost" size="sm" :disabled="i === draft.steps.length - 1" :aria-label="$t('schedules.moveDown')" @click="moveStep(i, 1)">↓</AppButton>
            <AppButton variant="ghost" size="sm" :disabled="draft.steps.length === 1" :aria-label="$t('schedules.removeStep')" @click="draft.steps.splice(i, 1)">✕</AppButton>
          </div>
        </div>
        <AppButton
          class="schedule-editor__add"
          variant="ghost"
          size="sm"
          :disabled="draft.steps.length >= MAX_STEPS"
          @click="draft.steps.push(newStep())"
        >
          {{ $t('schedules.addStep') }}
        </AppButton>
      </fieldset>

      <ToggleRow v-model="draft.enabled" :label="$t('schedules.fields.enabled')" />

      <p v-if="props.error" class="schedule-editor__error" role="alert">{{ props.error }}</p>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="props.saving" @click="emit('cancel')">
        {{ $t('common.cancel') }}
      </AppButton>
      <AppButton variant="primary" size="md" :loading="props.saving" :disabled="props.saving" @click="emit('save', toPayload())">
        {{ $t('common.save') }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.schedule-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-1) 0;
}

.schedule-editor__input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 6px var(--space-3);
  font: inherit;
  font-size: var(--text-sm);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s ease;
}

.schedule-editor__input:focus {
  border-color: var(--primary);
}

.schedule-editor__input--short {
  max-width: 160px;
}

.schedule-editor__input--mono {
  font-family: var(--font-mono);
}

.schedule-editor__fieldset {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.schedule-editor__legend {
  padding: 0;
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.schedule-editor__hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.schedule-editor__days {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.schedule-editor__day {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.schedule-editor__day input {
  accent-color: var(--primary);
}

.schedule-editor__step {
  display: grid;
  grid-template-columns: 80px 120px minmax(0, 1fr) auto;
  gap: var(--space-2);
  align-items: center;
}

.schedule-editor__step--head {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.schedule-editor__step-actions {
  display: flex;
  gap: 2px;
}

.schedule-editor__add {
  align-self: flex-start;
}

.schedule-editor__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--danger);
}

@media (max-width: 600px) {
  .schedule-editor__step {
    grid-template-columns: 70px minmax(0, 1fr);
  }

  .schedule-editor__step--head {
    display: none;
  }
}
</style>
