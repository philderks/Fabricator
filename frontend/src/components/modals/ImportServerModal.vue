<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import BaseModal from './BaseModal.vue'
import AppButton from '../ui/AppButton.vue'
import FormField from '../ui/FormField.vue'
import { inspectServerImport, importServer, getServerInstallProgress } from '../../api/servers'
import { createProgressPoller, lostContactMessage, POLL_INTERVAL_MS } from '../../utils/pollProgress'
import { t, te } from '../../i18n'

const props = defineProps({
  show: { type: Boolean, required: true }
})
const emit = defineEmits(['close', 'imported'])

const LOADERS = ['fabric', 'quilt', 'neoforge', 'forge', 'paper', 'purpur', 'folia', 'pufferfish', 'vanilla']

const path = ref('')
const detected = ref(null)
const form = ref({})
const mode = ref('copy')
const inspecting = ref(false)
const error = ref(null)
// null | 'running' | 'done' | 'failed'
const state = ref(null)
const progress = ref(null)
const server = ref(null)
let pollTimer = null

watch(() => props.show, (open) => {
  if (!open) return
  path.value = ''
  detected.value = null
  mode.value = 'copy'
  error.value = null
  state.value = null
  progress.value = null
  server.value = null
})

onBeforeUnmount(() => clearInterval(pollTimer))

const busy = computed(() => inspecting.value || state.value === 'running')

const phaseLabel = computed(() => {
  const key = `importServer.phases.${progress.value?.phase}`
  return te(key) ? t(key) : t('importServer.phases.starting')
})

async function inspect() {
  error.value = null
  detected.value = null
  inspecting.value = true
  try {
    const info = await inspectServerImport(path.value.trim())
    detected.value = info
    form.value = {
      name: info.name || '',
      loader: info.loader || '',
      version: info.version || '',
      port: info.port || 25565
    }
  } catch (err) {
    error.value = err?.message || t('importServer.inspectFailed')
  } finally {
    inspecting.value = false
  }
}

async function submit() {
  if (!form.value.name?.trim() || !form.value.loader || !form.value.version?.trim()) {
    error.value = t('importServer.fieldsRequired')
    return
  }
  error.value = null
  state.value = 'running'
  try {
    const created = await importServer({
      path: detected.value.path,
      mode: mode.value,
      name: form.value.name.trim(),
      loader: form.value.loader,
      version: form.value.version.trim(),
      port: form.value.port
    })
    server.value = created
    progress.value = created.progress
    watchProgress(created.id)
  } catch (err) {
    state.value = null
    error.value = err?.message || t('importServer.failed')
  }
}

function watchProgress(serverId) {
  const poll = createProgressPoller(() => getServerInstallProgress(serverId))
  pollTimer = setInterval(async () => {
    const result = await poll()
    // A slow tick can land after the final one; it must not overwrite it.
    if (state.value !== 'running' || result.status === 'retry') return
    if (result.status === 'giveup') {
      clearInterval(pollTimer)
      state.value = 'failed'
      progress.value = { error: lostContactMessage() }
      return
    }
    progress.value = result.progress
    if (!result.progress.active) {
      clearInterval(pollTimer)
      state.value = result.progress.phase === 'done' ? 'done' : 'failed'
    }
  }, POLL_INTERVAL_MS)
}

function close() {
  if (state.value === 'running') return
  if (state.value === 'done') emit('imported', server.value)
  emit('close')
}
</script>

<template>
  <BaseModal
    :show="props.show"
    :title="$t('importServer.title')"
    size="medium"
    :close-on-escape="!busy"
    @close="close"
  >
    <div v-if="state === 'running'" class="import-server__status">
      <div class="import-server__spinner" :aria-label="$t('common.working')"></div>
      <p>{{ phaseLabel }}</p>
    </div>

    <div v-else-if="state === 'done'" class="import-server__status">
      <p>{{ $t('importServer.done', { name: server?.name }) }}</p>
      <p v-if="progress?.mods_total" class="import-server__muted">
        {{ $t('importServer.modsLinked', { linked: progress.mods_linked, total: progress.mods_total }) }}
      </p>
      <p v-if="progress?.mods_link_error" class="import-server__muted">{{ $t('importServer.modsLinkFailed') }}</p>
    </div>

    <div v-else-if="state === 'failed'" class="import-server__status">
      <p class="import-server__error">{{ progress?.error || $t('importServer.failed') }}</p>
    </div>

    <form v-else class="import-server" @submit.prevent="detected ? submit() : inspect()">
      <p class="import-server__muted">{{ $t('importServer.intro') }}</p>

      <FormField :label="$t('importServer.path')" :hint="$t('importServer.pathHint')">
        <template #default="{ id, describedBy }">
          <div class="import-server__path">
            <input
              :id="id"
              v-model="path"
              type="text"
              :placeholder="$t('importServer.pathPlaceholder')"
              :aria-describedby="describedBy"
              :disabled="busy"
              @input="detected = null"
            >
            <AppButton variant="ghost" size="md" :loading="inspecting" :disabled="!path.trim()" @click="inspect">
              {{ $t('importServer.inspect') }}
            </AppButton>
          </div>
        </template>
      </FormField>

      <template v-if="detected">
        <ul v-if="detected.warnings.length" class="import-server__warnings" role="note">
          <li v-for="code in detected.warnings" :key="code">{{ $t(`importServer.warnings.${code}`) }}</li>
        </ul>

        <FormField :label="$t('properties.identity.name')">
          <template #default="{ id }">
            <input :id="id" v-model="form.name" type="text" required>
          </template>
        </FormField>

        <div class="import-server__row">
          <FormField :label="$t('properties.identity.modLoader')">
            <template #default="{ id }">
              <select :id="id" v-model="form.loader" required>
                <option value="" disabled>{{ $t('createServer.loaderNone') }}</option>
                <option v-for="loader in LOADERS" :key="loader" :value="loader">{{ loader }}</option>
              </select>
            </template>
          </FormField>
          <FormField :label="$t('createServer.minecraftVersion')">
            <template #default="{ id }">
              <input :id="id" v-model="form.version" type="text" placeholder="1.21.1" required>
            </template>
          </FormField>
          <FormField :label="$t('properties.identity.port')">
            <template #default="{ id }">
              <input :id="id" v-model.number="form.port" type="number" min="1" max="65535">
            </template>
          </FormField>
        </div>

        <p v-if="detected.modsCount" class="import-server__muted">
          {{ $t('importServer.modsFound', { count: detected.modsCount }) }}
        </p>

        <fieldset class="import-server__mode">
          <legend>{{ $t('importServer.mode') }}</legend>
          <label>
            <input v-model="mode" type="radio" value="copy">
            <span><strong>{{ $t('importServer.modeCopy') }}</strong> — {{ $t('importServer.modeCopyHint') }}</span>
          </label>
          <label>
            <input v-model="mode" type="radio" value="inplace">
            <span><strong>{{ $t('importServer.modeInplace') }}</strong> — {{ $t('importServer.modeInplaceHint') }}</span>
          </label>
        </fieldset>
      </template>

      <p v-if="error" class="import-server__error">{{ error }}</p>
    </form>

    <template #footer>
      <template v-if="!state">
        <AppButton variant="ghost" size="md" :disabled="busy" @click="close">{{ $t('common.cancel') }}</AppButton>
        <AppButton variant="primary" size="md" :disabled="!detected || busy" @click="submit">
          {{ $t('importServer.confirm') }}
        </AppButton>
      </template>
      <AppButton v-else-if="state !== 'running'" variant="primary" size="md" @click="close">
        {{ state === 'done' ? $t('importServer.open') : $t('common.close') }}
      </AppButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.import-server {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.import-server__path {
  display: flex;
  gap: var(--space-2);
}

.import-server__path input {
  flex: 1;
  min-width: 0;
}

.import-server__row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-4);
}

.import-server__row select,
.import-server__row input {
  width: 100%;
}

@media (max-width: 768px) {
  .import-server__row {
    grid-template-columns: 1fr;
  }
}

.import-server__muted {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.import-server__warnings {
  margin: 0;
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-6);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border: 1px solid var(--warning-dark);
  border-radius: var(--radius-md);
  background: rgba(245, 158, 11, 0.07);
}

.import-server__mode {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.import-server__mode legend {
  margin-bottom: var(--space-2);
  font-weight: 500;
  color: var(--text-primary);
}

.import-server__mode label {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  cursor: pointer;
}

.import-server__error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--danger);
}

.import-server__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
  text-align: center;
}

.import-server__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-tertiary);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: import-server-spin 0.8s linear infinite;
}

@keyframes import-server-spin {
  to { transform: rotate(360deg); }
}
</style>
