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
      <span v-if="unresolvedCount > 0" class="summary-warning">{{ unresolvedCount }} unresolved</span>
      <span v-else class="summary-ok">All resolved</span>
    </div>

    <div class="mod-list">
      <article v-for="mod in mods" :key="mod.path" class="mod-item">
        <div class="mod-header">
          <p class="mod-path">{{ mod.path }}</p>
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
        <p class="mod-reason">{{ mod.reason || 'No metadata available.' }}</p>
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
      selections: {}
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
    setSide(path, side) {
      this.selections = {
        ...this.selections,
        [path]: side
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
</style>
