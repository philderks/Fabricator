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
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          :disabled="!mods.length || checkingAll"
          @click="checkAllViaApi"
        >
          {{ checkingAll ? `Checking ${checkedCount}/${mods.length}...` : 'Check All via API' }}
        </button>
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
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              :disabled="rowChecking(mod.path)"
              @click="checkSingleViaApi(mod)"
            >
              {{ rowChecking(mod.path) ? 'Checking...' : 'Check via API' }}
            </button>
            <div class="toggle" role="group" :aria-label="`Side selection for ${mod.path}`">
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selectionFor(mod.path) === 'server' }"
                @click="setSide(mod.path, 'server')"
              >
                Server
              </button>
              <button
                type="button"
                class="toggle-btn"
                :class="{ active: selectionFor(mod.path) === 'client' }"
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
      <button class="btn btn-secondary" :disabled="loading" @click="handleCancel">
        Cancel
      </button>
      <button
        class="btn btn-primary"
        :disabled="loading || unresolvedCount > 0"
        @click="handleConfirm"
      >
        <span v-if="loading" class="btn-loading"></span>
        Apply Decisions
      </button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'
import { getModDetails, searchMods } from '../../api/modrinth'

export default {
  name: 'ModSideDecisionModal',
  components: {
    BaseModal
  },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    mods: {
      type: Array,
      default: () => []
    },
    loading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['confirm', 'cancel', 'close'],
  data() {
    return {
      selections: {},
      checks: {},
      checkingAll: false,
      checkedCount: 0,
      apiError: ''
    }
  },
  computed: {
    unresolvedCount() {
      return this.mods.reduce((count, mod) => {
        const selected = this.selections[mod.path]
        return selected === 'server' || selected === 'client' ? count : count + 1
      }, 0)
    }
  },
  methods: {
    selectionFor(path) {
      return this.selections[path] || ''
    },
    rowChecking(path) {
      return this.checks[path]?.state === 'checking'
    },
    apiCheckSummary(path) {
      const check = this.checks[path]
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
    },
    setSide(path, side) {
      this.selections = {
        ...this.selections,
        [path]: side
      }
    },
    deriveSearchQuery(path) {
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
    },
    async checkModViaApi(mod) {
      const path = mod?.path || ''
      const query = this.deriveSearchQuery(path)
      this.checks = {
        ...this.checks,
        [path]: { state: 'checking', message: '', recommendation: '', serverSide: '', projectTitle: '' }
      }

      try {
        const search = await searchMods({
          query,
          version: this.mcVersion || '',
          loader: this.loader || '',
          limit: 5,
          offset: 0
        })

        const hits = Array.isArray(search?.hits) ? search.hits : []
        if (!hits.length) {
          this.checks = {
            ...this.checks,
            [path]: {
              state: 'done',
              message: 'No Modrinth search result found.',
              recommendation: '',
              serverSide: '',
              projectTitle: ''
            }
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
          this.setSide(path, recommendation)
        }

        this.checks = {
          ...this.checks,
          [path]: {
            state: 'done',
            message: '',
            recommendation,
            serverSide,
            projectTitle
          }
        }
      } catch (error) {
        this.checks = {
          ...this.checks,
          [path]: {
            state: 'error',
            message: error?.message || 'API check failed.',
            recommendation: '',
            serverSide: '',
            projectTitle: ''
          }
        }
      }
    },
    async checkSingleViaApi(mod) {
      this.apiError = ''
      await this.checkModViaApi(mod)
    },
    async checkAllViaApi() {
      this.apiError = ''
      const maxSafe = 120
      if (this.mods.length > maxSafe) {
        this.apiError = `Too many mods to check in one run (${this.mods.length}). Please keep it below ${maxSafe} or check individually.`
        return
      }

      this.checkingAll = true
      this.checkedCount = 0
      try {
        for (const mod of this.mods) {
          await this.checkModViaApi(mod)
          this.checkedCount += 1
        }
      } finally {
        this.checkingAll = false
      }
    },
    handleCancel() {
      if (this.loading) {
        return
      }
      this.$emit('cancel')
      this.$emit('close')
    },
    handleConfirm() {
      if (this.loading || this.unresolvedCount > 0) {
        return
      }
      const payload = {}
      for (const mod of this.mods) {
        const selected = this.selections[mod.path]
        if (selected === 'server' || selected === 'client') {
          payload[mod.path] = selected
        }
      }
      this.$emit('confirm', payload)
    },
    resetSelections() {
      const initial = {}
      for (const mod of this.mods) {
        initial[mod.path] = ''
      }
      this.selections = initial
      const nextChecks = {}
      for (const mod of this.mods) {
        nextChecks[mod.path] = {
          state: 'idle',
          message: '',
          recommendation: '',
          serverSide: '',
          projectTitle: ''
        }
      }
      this.checks = nextChecks
      this.apiError = ''
      this.checkingAll = false
      this.checkedCount = 0
    }
  },
  watch: {
    show(value) {
      if (value) {
        this.resetSelections()
      }
    },
    mods() {
      if (this.show) {
        this.resetSelections()
      }
    }
  }
}
</script>

<style scoped>
.intro {
  margin-bottom: 0.85rem;
}

.intro-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.intro-text {
  margin: 0.35rem 0 0;
  color: var(--text-secondary);
  line-height: 1.45;
}

.summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 0.85rem;
}

.summary-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
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
  gap: 0.65rem;
  max-height: min(52vh, 480px);
  overflow: auto;
  padding-right: 0.25rem;
}

.mod-item {
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 0.75rem;
  background: color-mix(in oklch, var(--bg-secondary) 86%, transparent);
}

.mod-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}

.mod-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.mod-path {
  margin: 0;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.mod-reason {
  margin: 0.5rem 0 0;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.4;
}

.mod-api-result {
  margin: 0.35rem 0 0;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.toggle {
  display: inline-flex;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  padding: 0.2rem;
  background: var(--bg-primary);
}

.toggle-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 999px;
  padding: 0.35rem 0.8rem;
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
}

.toggle-btn.active {
  background: color-mix(in oklch, var(--primary) 18%, transparent);
  color: var(--text-primary);
}

.btn-sm {
  padding: 0.35rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 600;
}

.api-error {
  margin: 0 0 0.75rem;
  color: var(--danger, #d14343);
  font-size: 0.86rem;
}
</style>
