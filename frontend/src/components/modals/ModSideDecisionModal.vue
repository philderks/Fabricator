<template>
  <BaseModal
    :show="show"
    title="Classify Uncertain Mods"
    size="large"
    @close="handleCancel"
  >
    <div class="intro">
      <p class="intro-title">Some mods could not be classified automatically.</p>
      <p class="intro-text">
        Choose for each mod whether it should be treated as <strong>Server</strong> (keep/install)
        or <strong>Client</strong> (skip for dedicated server).
      </p>
    </div>

    <div class="summary">
      <span>{{ mods.length }} mods require a decision</span>
      <div class="summary-actions">
        <AppButton
          variant="ghost"
          size="sm"
          :disabled="!mods.length || checkingAll"
          @click="checkAllViaApi"
        >
          {{ checkingAll ? `Checking ${checkedCount}/${mods.length}...` : 'Check All via API' }}
        </AppButton>
        <span v-if="unresolvedCount > 0" class="summary-warning">{{ unresolvedCount }} unresolved</span>
        <span v-else class="summary-ok">All resolved</span>
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
              {{ rowChecking(mod.path) ? 'Checking...' : 'Check via API' }}
            </AppButton>
            <div class="toggle" role="group" :aria-label="`Side selection for ${mod.path}`">
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selections[mod.path] === 'server' }"
                @click="setSide(mod.path, 'server')"
              >
                Server
              </button>
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selections[mod.path] === 'client' }"
                @click="setSide(mod.path, 'client')"
              >
                Client
              </button>
            </div>
          </div>
        </div>
        <p class="mod-reason">{{ mod.reason || 'No metadata available.' }}</p>
        <p v-if="apiCheckSummary(mod.path)" class="mod-api-result">{{ apiCheckSummary(mod.path) }}</p>
      </article>
    </div>

    <template #footer>
      <AppButton variant="ghost" size="md" :disabled="loading" @click="handleCancel">
        Cancel
      </AppButton>
      <AppButton
        variant="primary"
        size="md"
        :disabled="loading || unresolvedCount > 0"
        :loading="loading"
        @click="handleConfirm"
      >
        Apply Decisions
      </AppButton>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import { getModDetails, searchMods } from '../../api/modrinth'

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
    return 'Checking Modrinth API...'
  }
  if (check.state === 'error') {
    return check.message || 'API check failed.'
  }
  const recommendation = check.recommendation ? `Recommendation: ${check.recommendation.toUpperCase()}. ` : ''
  const serverSide = check.serverSide ? `server_side=${check.serverSide}. ` : ''
  const project = check.projectTitle ? `Match: ${check.projectTitle}.` : 'No exact match found.'
  return `${recommendation}${serverSide}${project}`
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

async function checkModViaApi(mod) {
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
    })

    const hits = Array.isArray(search?.hits) ? search.hits : []
    if (!hits.length) {
      checks.value = {
        ...checks.value,
        [path]: { state: 'done', message: 'No Modrinth search result found.', recommendation: '', serverSide: '', projectTitle: '' }
      }
      return
    }

    const projectId = hits[0].project_id
    const projectTitle = hits[0].title || hits[0].slug || projectId
    const details = await getModDetails(projectId)
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
    checks.value = {
      ...checks.value,
      [path]: { state: 'error', message: error?.message || 'API check failed.', recommendation: '', serverSide: '', projectTitle: '' }
    }
  }
}

async function checkSingleViaApi(mod) {
  apiError.value = ''
  await checkModViaApi(mod)
}

async function checkAllViaApi() {
  apiError.value = ''
  const maxSafe = 120
  if (props.mods.length > maxSafe) {
    apiError.value = `Too many mods to check in one run (${props.mods.length}). Please keep it below ${maxSafe} or check individually.`
    return
  }

  checkingAll.value = true
  checkedCount.value = 0
  try {
    for (const mod of props.mods) {
      await checkModViaApi(mod)
      checkedCount.value += 1
    }
  } finally {
    checkingAll.value = false
  }
}

function handleCancel() {
  if (props.loading) {
    return
  }
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
