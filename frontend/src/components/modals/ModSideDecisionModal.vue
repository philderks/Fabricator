<template>
  <BaseModal
    :show="show"
    :title="$t('sideDecision.title')"
    size="large"
    @close="handleCancel"
  >
    <div class="intro">
      <p class="intro-title">{{ $t('sideDecision.introTitle') }}</p>
      <i18n-t keypath="sideDecision.intro" tag="p" class="intro-text">
        <template #server><strong>{{ $t('sideDecision.server') }}</strong></template>
        <template #client><strong>{{ $t('sideDecision.client') }}</strong></template>
      </i18n-t>
    </div>

    <div class="summary">
      <span>{{ $t('sideDecision.needDecision', mods.length) }}</span>
      <div class="summary-actions">
        <AppButton
          variant="ghost"
          size="sm"
          :disabled="!mods.length || checkingAll"
          @click="checkAllViaApi"
        >
          {{ checkingAll ? $t('sideDecision.checkingProgress', { done: checkedCount, total: mods.length }) : $t('sideDecision.checkAll') }}
        </AppButton>
        <span v-if="unresolvedCount > 0" class="summary-warning">{{ $t('sideDecision.unresolved', { n: unresolvedCount }) }}</span>
        <span v-else class="summary-ok">{{ $t('sideDecision.allResolved') }}</span>
      </div>
    </div>

    <p v-if="apiError" class="api-error">{{ apiError }}</p>

    <div class="mod-list">
      <article v-for="mod in mods" :key="mod.path" class="mod-item">
        <div class="mod-header">
          <p class="mod-path">{{ mod.path }}</p>
          <div class="mod-actions">
            <AppButton
              variant="ghost"
              size="sm"
              :disabled="rowChecking(mod.path)"
              @click="checkSingleViaApi(mod)"
            >
              {{ rowChecking(mod.path) ? $t('sideDecision.checking') : $t('sideDecision.check') }}
            </AppButton>
            <div class="toggle" role="group" :aria-label="$t('sideDecision.sideSelection', { path: mod.path })">
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selections[mod.path] === 'server' }"
                @click="setSide(mod.path, 'server')"
              >
                {{ $t('sideDecision.server') }}
              </button>
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selections[mod.path] === 'client' }"
                @click="setSide(mod.path, 'client')"
              >
                {{ $t('sideDecision.client') }}
              </button>
            </div>
          </div>
        </div>
        <p class="mod-reason">{{ mod.reason || $t('sideDecision.noMetadata') }}</p>
        <p v-if="apiCheckSummary(mod.path)" class="mod-api-result">{{ apiCheckSummary(mod.path) }}</p>
      </article>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="loading" @click="handleCancel">
        {{ $t('common.cancel') }}
      </AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="loading || unresolvedCount > 0"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ $t('sideDecision.apply') }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { getModDetails, searchMods } from '../../api/modrinth'
import { pLimit, withBackoff } from '../../api/throttle'
import { t } from '../../i18n'

const props = defineProps({
  show: { type: Boolean, required: true },
  mods: { type: Array, default: () => [] },
  mcVersion: { type: String, default: '' },
  loader: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['confirm', 'cancel', 'close'])

const selections = ref({})
const checks = ref({})
const checkingAll = ref(false)
const checkedCount = ref(0)
const apiError = ref('')
const inflightController = ref(null)

const unresolvedCount = computed(() =>
  props.mods.reduce((count, mod) => {
    const selected = selections.value[mod.path]
    return selected === 'server' || selected === 'client' ? count : count + 1
  }, 0)
)

function rowChecking(path) {
  return checks.value[path]?.state === 'checking'
}

function apiCheckSummary(path) {
  const check = checks.value[path]
  if (!check || check.state === 'idle') {
    return ''
  }
  if (check.state === 'checking') {
    return t('sideDecision.checkingApi')
  }
  if (check.state === 'error') {
    return check.message || t('sideDecision.checkFailed')
  }
  const side = check.recommendation === 'server' ? t('sideDecision.server') : t('sideDecision.client')
  const recommendation = check.recommendation ? t('sideDecision.recommendation', { side: side.toUpperCase() }) : ''
  const serverSide = check.serverSide ? `server_side=${check.serverSide}.` : ''
  const project = check.projectTitle ? t('sideDecision.match', { title: check.projectTitle }) : t('sideDecision.noExactMatch')
  return [recommendation, serverSide, project].filter(Boolean).join(' ')
}

function setSide(path, side) {
  selections.value = { ...selections.value, [path]: side }
}

function deriveSearchQuery(path) {
  const fileName = String(path || '').split('/').pop() || String(path || '')
  const base = fileName
    .replace(/\.jar$/i, '')
    .replace(/[-_+]?mc\d+(?:\.\d+){1,3}.*/i, '')
    .replace(/[-_+]?fabric.*/i, '')
    .replace(/[-_+]?forge.*/i, '')
    .replace(/[-_+]?quilt.*/i, '')
    .replace(/[0-9]+(?:\.[0-9]+){1,4}.*/i, '')
    .replace(/[_+.-]+/g, ' ')
    .trim()
  return base || fileName
}

async function checkModViaApi(mod, { signal } = {}) {
  const path = mod?.path || ''
  const query = deriveSearchQuery(path)
  checks.value = {
    ...checks.value,
    [path]: { state: 'checking', message: '', recommendation: '', serverSide: '', projectTitle: '' }
  }

  try {
    const search = await searchMods({
      query,
      version: props.mcVersion || '',
      loader: props.loader || '',
      limit: 5,
      offset: 0
    }, { signal })

    const hits = Array.isArray(search?.hits) ? search.hits : []
    if (!hits.length) {
      checks.value = {
        ...checks.value,
        [path]: { state: 'done', message: t('sideDecision.noSearchResult'), recommendation: '', serverSide: '', projectTitle: '' }
      }
      return
    }

    const projectId = hits[0].project_id
    const projectTitle = hits[0].title || hits[0].slug || projectId
    const details = await getModDetails(projectId, { signal })
    const serverSide = String(details?.server_side || '').toLowerCase()

    let recommendation = ''
    if (serverSide === 'required' || serverSide === 'optional') {
      recommendation = 'server'
    } else if (serverSide === 'unsupported') {
      recommendation = 'client'
    }

    if (recommendation) {
      setSide(path, recommendation)
    }

    checks.value = {
      ...checks.value,
      [path]: { state: 'done', message: '', recommendation, serverSide, projectTitle }
    }
  } catch (error) {
    // Intentional cancellation (modal close) — drop the row back to idle and
    // do NOT surface an "API check failed" message; that's reserved for
    // actual API errors so the UX stays honest.
    if (error?.name === 'AbortError') {
      checks.value = {
        ...checks.value,
        [path]: { state: 'idle', message: '', recommendation: '', serverSide: '', projectTitle: '' }
      }
      return
    }
    checks.value = {
      ...checks.value,
      [path]: { state: 'error', message: error?.message || t('sideDecision.checkFailed'), recommendation: '', serverSide: '', projectTitle: '' }
    }
    // Re-throw so a caller that wraps this in withBackoff (checkAllViaApi) can
    // actually retry transient failures (429/503). Previously this was
    // swallowed, so withBackoff always saw success and never retried. Single
    // checks catch and ignore it (the per-row error state is already set).
    throw error
  }
}

async function checkSingleViaApi(mod) {
  apiError.value = ''
  // Single-row checks ride the modal's shared abort controller so a modal
  // close cancels them too. A fresh controller is created lazily.
  if (!inflightController.value) {
    inflightController.value = new AbortController()
  }
  try {
    await checkModViaApi(mod, { signal: inflightController.value.signal })
  } catch {
    // A single check has no retry; the per-row error/idle state is already
    // recorded inside checkModViaApi. Swallow the re-thrown error so it doesn't
    // surface as an unhandled rejection.
  }
}

async function checkAllViaApi() {
  apiError.value = ''
  const maxSafe = 120
  if (props.mods.length > maxSafe) {
    apiError.value = t('sideDecision.tooMany', { count: props.mods.length, max: maxSafe })
    return
  }

  // Fresh controller per run — old aborted controllers can't be reused.
  inflightController.value = new AbortController()
  const signal = inflightController.value.signal
  const localLimiter = pLimit(4)

  checkingAll.value = true
  checkedCount.value = 0
  try {
    const tasks = props.mods.map((mod) =>
      localLimiter(
        () => withBackoff(
          () => checkModViaApi(mod, { signal }),
          { signal, retries: 3 }
        ),
        { signal }
      ).then(
        () => { checkedCount.value += 1 },
        (error) => {
          // Limiter/withBackoff abort just stops the row; don't crash the run.
          if (error?.name !== 'AbortError') {
            // checkModViaApi already records per-row error state; we just
            // need to advance the progress counter so the UI doesn't stall.
            checkedCount.value += 1
          }
        }
      )
    )
    await Promise.allSettled(tasks)
  } finally {
    checkingAll.value = false
  }
}

function handleCancel() {
  if (props.loading) {
    return
  }
  // Cancel any in-flight API checks BEFORE we tear down state so their
  // rejections don't race state resets.
  inflightController.value?.abort()
  emit('cancel')
  emit('close')
}

function handleConfirm() {
  if (props.loading || unresolvedCount.value > 0) {
    return
  }
  const payload = {}
  for (const mod of props.mods) {
    const selected = selections.value[mod.path]
    if (selected === 'server' || selected === 'client') {
      payload[mod.path] = selected
    }
  }
  emit('confirm', payload)
}

function resetSelections() {
  const initial = {}
  const nextChecks = {}
  for (const mod of props.mods) {
    initial[mod.path] = ''
    nextChecks[mod.path] = { state: 'idle', message: '', recommendation: '', serverSide: '', projectTitle: '' }
  }
  selections.value = initial
  checks.value = nextChecks
  apiError.value = ''
  checkingAll.value = false
  checkedCount.value = 0
}

watch(() => props.show, (value) => {
  if (value) {
    resetSelections()
  } else {
    // Modal closed via X / overlay / parent toggle — abort first, then
    // reset so in-flight check promises rejecting AbortError can't write
    // back into freshly-reset row state.
    inflightController.value?.abort()
    inflightController.value = null
    resetSelections()
  }
})

watch(() => props.mods, () => {
  if (props.show) {
    resetSelections()
  }
})
</script>

<style scoped>
.intro {
  margin-bottom: var(--space-3);
}

.intro-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 700;
  color: var(--text-primary);
}

.intro-text {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
}

.summary-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.summary-warning {
  color: var(--warning, #d97706);
  font-weight: 700;
}

.summary-ok {
  color: var(--success, #22a06b);
  font-weight: 700;
}

.mod-list {
  display: grid;
  gap: var(--space-2);
  max-height: min(52vh, 480px);
  overflow: auto;
  padding-right: var(--space-1);
}

.mod-item {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  background: color-mix(in oklch, var(--bg-secondary) 86%, transparent);
}

.mod-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  align-items: center;
  flex-wrap: wrap;
}

.mod-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.mod-path {
  margin: 0;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.mod-reason {
  margin: var(--space-2) 0 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.mod-api-result {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.toggle {
  display: inline-flex;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: var(--space-1);
  background: var(--bg-primary);
}

.toggle-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 700;
  cursor: pointer;
}

.toggle-btn.active {
  background: var(--primary);
  color: #ffffff;
}

.api-error {
  margin: 0 0 var(--space-3);
  color: var(--danger, #d14343);
  font-size: var(--text-sm);
}
</style>
