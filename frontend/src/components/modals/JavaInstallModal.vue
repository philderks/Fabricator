<template>
  <BaseModal
    :show="show"
    title="Java Required"
    size="small"
    @close="$emit('close')"
  >
    <div class="java-content">
      <div class="java-icon">
        <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 20H22L12 2Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M12 10V14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <circle cx="12" cy="17.5" r="0.75" fill="currentColor"/>
        </svg>
      </div>

      <p class="java-heading">Java 21 is not installed</p>
      <p class="java-subtext">
        A Minecraft server requires <strong>Java 21</strong> or later to run.
        Download and install it, then try starting your server again.
      </p>

      <div class="java-platform">
        <span class="platform-label">Your platform:</span>
        <span class="platform-value">{{ platformLabel }}</span>
      </div>

      <div v-if="platform === 'linux'" class="java-tip">
        <p class="tip-title">Quick install via terminal</p>
        <code class="tip-code">sudo apt install openjdk-21-jre-headless</code>
        <p class="tip-note">Works on Debian / Ubuntu. For other distros, use the download button below.</p>
      </div>

      <div v-else-if="platform === 'windows'" class="java-tip">
        <p class="tip-title">Installation steps</p>
        <ol class="tip-steps">
          <li>Download the <strong>.msi</strong> installer from the link below.</li>
          <li>Run the installer and follow the prompts.</li>
          <li>Restart Fabricator and start your server again.</li>
        </ol>
      </div>

      <div v-else-if="platform === 'darwin'" class="java-tip">
        <p class="tip-title">Installation steps</p>
        <ol class="tip-steps">
          <li>Download the <strong>.pkg</strong> installer from the link below.</li>
          <li>Run the installer and follow the prompts.</li>
          <li>Restart Fabricator and start your server again.</li>
        </ol>
      </div>
    </div>

    <template #footer>
      <button class="btn btn-secondary" @click="$emit('close')">Close</button>
      <a
        :href="downloadUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="btn btn-primary"
        @click="$emit('close')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="margin-right: 6px">
          <path d="M12 3v12M12 15l-4-4M12 15l4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M3 20h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        Download Java 21
      </a>
    </template>
  </BaseModal>
</template>

<script>
import BaseModal from './BaseModal.vue'

const PLATFORM_LABELS = {
  windows: 'Windows',
  darwin:  'macOS',
  linux:   'Linux',
}

export default {
  name: 'JavaInstallModal',
  components: { BaseModal },
  props: {
    show: {
      type: Boolean,
      required: true
    },
    platform: {
      type: String,
      default: ''
    },
    downloadUrl: {
      type: String,
      default: 'https://adoptium.net/temurin/releases/?version=21'
    }
  },
  emits: ['close'],
  computed: {
    platformLabel() {
      return PLATFORM_LABELS[this.platform] || 'Unknown'
    }
  }
}
</script>

<style scoped>
.java-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
  padding: 8px 0;
}

.java-icon {
  color: var(--warning, #f59e0b);
  display: flex;
  align-items: center;
  justify-content: center;
}

.java-heading {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.java-subtext {
  font-size: 0.9375rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
}

.java-platform {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 0.875rem;
  width: 100%;
  justify-content: center;
}

.platform-label {
  color: var(--text-secondary);
}

.platform-value {
  color: var(--text-primary);
  font-weight: 500;
}

.java-tip {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  text-align: left;
}

.tip-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 10px 0;
}

.tip-code {
  display: block;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--primary, #22c55e);
  word-break: break-all;
  margin-bottom: 8px;
}

.tip-note {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.tip-steps {
  margin: 0;
  padding-left: 20px;
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.8;
}

.tip-steps li strong {
  color: var(--text-primary);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
}
</style>
