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
      <AppButton variant="ghost" size="md" @click="$emit('cancel')">
        Abbrechen
      </AppButton>
      <AppButton
        :variant="installButtonVariant"
        size="md"
        :disabled="!selectedVersion && !serverVersion && !versionsToShow.length"
        @click="confirmSelection"
      >
        Version installieren
      </AppButton>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'

export default {
  name: 'CompatibilityConfirmModal',
  components: { BaseModal, AppButton },
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
    installButtonVariant() {
      switch (this.status) {
        case 'full':
          return 'primary'
        case 'likely':
          return 'warning'
        default:
          return 'danger'
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
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  margin-bottom: var(--space-4);
  align-items: center;
}

.status-banner svg {
  flex-shrink: 0;
}

.status-title {
  font-size: var(--text-base);
  font-weight: 600;
  margin: 0;
  line-height: var(--leading-tight);
}

.status-description {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.status-banner--full {
  background: color-mix(in oklch, var(--success) 12%, transparent);
  border-color: color-mix(in oklch, var(--success) 28%, transparent);
  color: var(--success);
}

.status-banner--likely {
  background: color-mix(in oklch, var(--warning) 12%, transparent);
  border-color: color-mix(in oklch, var(--warning) 28%, transparent);
  color: var(--warning);
}

.status-banner--danger,
.status-banner--unknown {
  background: color-mix(in oklch, var(--danger) 12%, transparent);
  border-color: color-mix(in oklch, var(--danger) 28%, transparent);
  color: var(--danger);
}

.modal-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.version-list {
  margin-top: var(--space-4);
}

.version-list__label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-bottom: var(--space-2);
}

.version-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chip {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-color);
  font-size: var(--text-xs);
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
  background: color-mix(in oklch, var(--primary) 12%, transparent);
  border-color: color-mix(in oklch, var(--primary) 28%, transparent);
  color: var(--primary);
}

.chip--highlight {
  box-shadow: 0 0 0 1px color-mix(in oklch, var(--primary) 40%, transparent);
}
</style>
