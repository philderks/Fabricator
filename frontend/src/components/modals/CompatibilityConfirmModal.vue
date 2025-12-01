<template>
  <BaseModal
    :show="show"
    title="Compatibility Warning"
    size="medium"
    @close="$emit('close')"
  >
    <div class="status-banner" :class="statusClass">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" />
        <path d="M12 10V14" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        <path d="M12 18H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
      <div>
        <p class="status-title">{{ statusTitle }}</p>
        <p class="status-description">{{ statusDescription }}</p>
      </div>
    </div>

    <div class="modal-content">
      <p class="modal-text">
        <strong>{{ modTitle }}</strong> wurde nicht ausdrücklich für
        <strong>{{ serverVersion }}</strong> veröffentlicht.
        Prüfe die unterstützten Versionen, bevor du fortfährst.
      </p>

      <div v-if="versionsToShow.length" class="version-list">
        <p class="version-list__label">Wähle die Version, die installiert werden soll:</p>
        <div class="version-chips">
          <button
            v-for="version in versionsToShow"
            :key="version"
            type="button"
            class="chip chip--selectable"
            :class="{
              'chip--highlight': isServerVersion(version),
              'chip--selected': version === selectedVersion
            }"
            @click="selectVersion(version)"
          >
            {{ version }}
          </button>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="btn btn-secondary" @click="$emit('cancel')">
        Abbrechen
      </button>
      <button
        class="btn btn-danger"
        :disabled="!selectedVersion && !serverVersion && !versionsToShow.length"
        @click="confirmSelection"
      >
        Version installieren
      </button>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'

export default {
  name: 'CompatibilityConfirmModal',
  components: { BaseModal },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    modTitle: {
      type: String,
      default: ''
    },
    serverVersion: {
      type: String,
      default: ''
    },
    status: {
      type: String,
      default: 'unknown'
    },
    versions: {
      type: Array,
      default: () => []
    },
    initialSelectedVersion: {
      type: String,
      default: ''
    }
  },
  emits: ['confirm', 'cancel', 'close'],
  data() {
    return {
      selectedVersion: ''
    }
  },
  computed: {
    statusClass() {
      switch (this.status) {
        case 'full':
          return 'status-banner--full'
        case 'likely':
          return 'status-banner--likely'
        case 'unlikely':
        case 'unknown':
          return 'status-banner--danger'
        default:
          return 'status-banner--unknown'
      }
    },
    statusTitle() {
      switch (this.status) {
        case 'full':
          return 'Vollständig kompatibel'
        case 'likely':
          return 'Wahrscheinlich kompatibel'
        case 'unlikely':
          return 'Möglicherweise inkompatibel'
        default:
          return 'Kompatibilität unbekannt'
      }
    },
    statusDescription() {
      switch (this.status) {
        case 'full':
          return `${this.modTitle} unterstützt deine Server-Version ausdrücklich.`
        case 'likely':
          return `${this.modTitle} ist nicht offiziell für ${this.serverVersion} freigegeben, sollte aber funktionieren.`
        case 'unlikely':
          return `${this.modTitle} scheint nicht für ${this.serverVersion} geeignet zu sein.`
        default:
          return 'Wir konnten keine kompatiblen Versionen finden.'
      }
    },
    versionsToShow() {
      return this.versions
    },
    hasMoreVersions() {
      return false
    },
    extraCount() {
      return 0
    }
  },
  methods: {
    isServerVersion(version) {
      return this.serverVersion && version === this.serverVersion
    },
    selectVersion(version) {
      this.selectedVersion = version
    },
    confirmSelection() {
      const fallback = this.serverVersion || this.versions[0] || ''
      const chosen = this.selectedVersion || fallback
      this.$emit('confirm', chosen)
    },
    resetSelection() {
      if (this.initialSelectedVersion && this.versions.includes(this.initialSelectedVersion)) {
        this.selectedVersion = this.initialSelectedVersion
        return
      }
      if (this.serverVersion && this.versions.includes(this.serverVersion)) {
        this.selectedVersion = this.serverVersion
        return
      }
      this.selectedVersion = this.versions[0] || ''
    }
  },
  watch: {
    show(newVal) {
      if (newVal) {
        this.resetSelection()
      }
    },
    versions() {
      if (this.show) {
        this.resetSelection()
      }
    },
    initialSelectedVersion() {
      if (this.show) {
        this.resetSelection()
      }
    }
  }
}
</script>

<style scoped>
.status-banner {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 16px;
  align-items: center;
}

.status-banner svg {
  flex-shrink: 0;
}

.status-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.status-description {
  margin: 4px 0 0;
  font-size: 0.875rem;
}

.status-banner--full {
  background: color-mix(in oklch, var(--success) 20%, transparent);
  color: var(--success);
}

.status-banner--likely {
  background: color-mix(in oklch, var(--warning) 20%, transparent);
  color: var(--warning);
}

.status-banner--danger,
.status-banner--unknown {
  background: color-mix(in oklch, var(--danger) 15%, transparent);
  color: var(--danger);
}

.modal-text {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.version-list {
  margin-top: 16px;
}

.version-list__label {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.version-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: transparent;
  cursor: default;
}

.chip--selectable {
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}

.chip--selectable:hover {
  border-color: var(--primary);
}

.chip--selected {
  background: color-mix(in oklch, var(--primary) 20%, transparent);
  border-color: var(--primary);
  color: var(--primary);
}

.chip--highlight {
  box-shadow: 0 0 0 1px color-mix(in oklch, var(--primary) 40%, transparent);
}

button[disabled] {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
