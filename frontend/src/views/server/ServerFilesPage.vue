<script setup>
import { computed, defineAsyncComponent, nextTick, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import ConfirmModal from '../../components/modals/ConfirmModal.vue'
import { formatFileSize } from '../../utils/format'
import { copyToClipboard } from '../../utils/clipboard'
import { useServerStore } from '../../stores/server'

// Async-loaded so CodeMirror lands in its own chunk instead of the main bundle
// (the Files route is imported statically by the router).
const CodeEditor = defineAsyncComponent(() => import('../../components/ui/CodeEditor.vue'))

const store = useServerStore()

const editorRef = ref(null)
const codeEditorRef = ref(null)

// CC6: modal-based confirm instead of window.confirm. Local state with a
// promise-resolver lets the call sites keep their `if (!await ...) return`
// shape without pushing dialog state into the store (single consumer).
const showDiscardConfirm = ref(false)
let discardResolver = null

const confirmDiscardChanges = () => {
  if (!store.hasFileChanges) return Promise.resolve(true)
  return new Promise((resolve) => {
    discardResolver = resolve
    showDiscardConfirm.value = true
  })
}

const handleDiscardConfirm = () => {
  showDiscardConfirm.value = false
  if (discardResolver) {
    discardResolver(true)
    discardResolver = null
  }
}

const handleDiscardCancel = () => {
  showDiscardConfirm.value = false
  if (discardResolver) {
    discardResolver(false)
    discardResolver = null
  }
}

// Invalid-save confirm — same promise-resolver shape as the discard dialog, so
// onSave can keep its `if (!await ...) return` flow.
const hasSyntaxErrors = ref(false)
const showInvalidSaveConfirm = ref(false)
let invalidSaveResolver = null

const onValidity = ({ hasErrors }) => {
  hasSyntaxErrors.value = hasErrors
}

const confirmInvalidSave = () => {
  // Prefer the editor's synchronous, live check (no lint-debounce staleness);
  // fall back to the last emitted flag if the editor ref isn't resolved.
  const hasErrors = codeEditorRef.value?.hasErrors?.() ?? hasSyntaxErrors.value
  if (!hasErrors) return Promise.resolve(true)
  return new Promise((resolve) => {
    invalidSaveResolver = resolve
    showInvalidSaveConfirm.value = true
  })
}

const handleInvalidSaveConfirm = () => {
  showInvalidSaveConfirm.value = false
  if (invalidSaveResolver) {
    invalidSaveResolver(true)
    invalidSaveResolver = null
  }
}

const handleInvalidSaveCancel = () => {
  showInvalidSaveConfirm.value = false
  if (invalidSaveResolver) {
    invalidSaveResolver(false)
    invalidSaveResolver = null
  }
}

const onSave = async () => {
  if (store.fileEditor.loading || store.fileEditor.saving || !store.hasFileChanges) return
  if (!(await confirmInvalidSave())) return
  await store.saveFile()
}

// Warn before a hard reload/close drops unsaved edits. The in-app file-switch,
// close, and route-leave paths are handled by confirmDiscardChanges.
const beforeUnloadHandler = (event) => {
  event.preventDefault()
  event.returnValue = ''
}

watch(
  () => store.hasFileChanges,
  (dirty) => {
    if (dirty) {
      window.addEventListener('beforeunload', beforeUnloadHandler)
    } else {
      window.removeEventListener('beforeunload', beforeUnloadHandler)
    }
  }
)

onBeforeRouteLeave(async () => {
  if (!(await confirmDiscardChanges())) return false
  return true
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', beforeUnloadHandler)
  clearTimeout(searchTimer)
  store.clearFileSearch()
  if (discardResolver) {
    discardResolver(false)
    discardResolver = null
  }
  if (invalidSaveResolver) {
    invalidSaveResolver(false)
    invalidSaveResolver = null
  }
})

// Callers confirm any pending discard first, so a search hit doesn't prompt twice.
const openFileAndScroll = async (path) => {
  await store.openFile(path)
  // Scroll the editor into view after Vue paints it.
  await nextTick()
  if (editorRef.value) {
    const el = editorRef.value.$el || editorRef.value
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }
}

const onFileClick = async (entry) => {
  if (!(await confirmDiscardChanges())) return
  await openFileAndScroll(entry.relativePath || entry.name)
}

// Search runs against the whole server tree, so it's debounced rather than
// fired per keystroke.
const searchInput = ref('')
let searchTimer = null

const runSearch = (value) => {
  clearTimeout(searchTimer)
  if (!value.trim()) {
    store.clearFileSearch()
    return
  }
  searchTimer = setTimeout(() => store.searchFiles(value), 250)
}

watch(searchInput, runSearch)

const onSearchSubmit = () => {
  clearTimeout(searchTimer)
  if (searchInput.value.trim()) store.searchFiles(searchInput.value)
}

const onClearSearch = () => {
  searchInput.value = ''
  clearTimeout(searchTimer)
  store.clearFileSearch()
}

// Folder hits navigate into the folder; file hits leave search mode, park the
// browser on the file's folder, and open it in the editor.
const onSearchHitClick = async (entry) => {
  if (entry.isDir) {
    searchInput.value = ''
    store.revealSearchHit(entry)
    return
  }
  if (!(await confirmDiscardChanges())) return
  searchInput.value = ''
  store.revealSearchHit(entry)
  await openFileAndScroll(entry.relativePath)
}

const onCloseEditor = async () => {
  if (!(await confirmDiscardChanges())) return
  store.closeFile()
}

const breadcrumbs = computed(() => {
  const path = store.fileBrowser.currentPath || ''
  const parts = path.split('/').filter(Boolean)
  const crumbs = [{ label: 'server', path: '' }]
  let acc = ''
  for (const p of parts) {
    acc = acc ? `${acc}/${p}` : p
    crumbs.push({ label: p, path: acc })
  }
  return crumbs
})

const formatModified = (iso) => {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

const onCrumbClick = (crumb) => {
  if (crumb.path === store.fileBrowser.currentPath) return
  store.openFileBrowser(crumb.path)
}

const onRefresh = () => store.openFileBrowser(store.fileBrowser.currentPath)
const canGoUp = computed(() => Boolean(store.fileBrowser.currentPath))

const copyState = ref('idle')
const onCopyPath = async () => {
  const path = store.fileBrowser.absolutePath
  if (!path) return
  const ok = await copyToClipboard(path)
  copyState.value = ok ? 'copied' : 'error'
  setTimeout(() => { copyState.value = 'idle' }, 1500)
}
</script>

<template>
  <div class="files-page">
    <div v-if="store.fileBrowser.absolutePath" class="files-page__location">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
        <path d="M2 3.5A1.5 1.5 0 013.5 2h2.5l1.5 2H11a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0111 13H3.5A1.5 1.5 0 012 11.5v-8z" />
      </svg>
      <code class="files-page__location-path">{{ store.fileBrowser.absolutePath }}</code>
      <button
        type="button"
        class="files-page__location-copy"
        :class="{ 'is-copied': copyState === 'copied', 'is-error': copyState === 'error' }"
        :title="copyState === 'copied' ? 'Copied!' : 'Copy path'"
        @click="onCopyPath"
      >
        <span v-if="copyState === 'copied'">Copied</span>
        <span v-else-if="copyState === 'error'">Failed</span>
        <span v-else>Copy</span>
      </button>
    </div>
    <div class="files-page__toolbar">
      <AppButton variant="ghost" size="sm" :disabled="!canGoUp" @click="store.goUpDirectory">↑ Up</AppButton>
      <nav class="files-page__crumbs" aria-label="Path">
        <template v-for="(crumb, i) in breadcrumbs" :key="i">
          <button
            type="button"
            class="files-page__crumb"
            :class="{ 'is-current': i === breadcrumbs.length - 1 }"
            :disabled="i === breadcrumbs.length - 1"
            @click="onCrumbClick(crumb)"
          >{{ crumb.label }}</button>
          <span v-if="i < breadcrumbs.length - 1" class="files-page__crumb-sep">/</span>
        </template>
      </nav>
      <div class="files-page__search">
        <svg class="files-page__search-icon" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <circle cx="6" cy="6" r="4" />
          <path d="M9 9l4 4" />
        </svg>
        <input
          v-model="searchInput"
          type="search"
          class="files-page__search-input"
          placeholder="Search all files…"
          aria-label="Search files by name"
          @keydown.enter.prevent="onSearchSubmit"
          @keydown.esc.prevent="onClearSearch"
        />
        <button
          v-if="searchInput"
          type="button"
          class="files-page__search-clear"
          title="Clear search"
          @click="onClearSearch"
        >×</button>
      </div>
      <AppButton variant="ghost" size="sm" :loading="store.fileBrowser.loading" @click="onRefresh">Refresh</AppButton>
    </div>

    <Panel v-if="store.fileSearch.active" :padded="false">
      <div v-if="store.fileSearch.loading" class="files-page__state">Searching…</div>
      <div v-else-if="store.fileSearch.error" class="files-page__state files-page__state--error">{{ store.fileSearch.error }}</div>
      <div v-else-if="!store.fileSearch.results.length" class="files-page__state">
        No files match “{{ store.fileSearch.query }}”.
      </div>
      <template v-else>
        <p class="files-page__search-summary">
          {{ store.fileSearch.results.length }}
          {{ store.fileSearch.results.length === 1 ? 'match' : 'matches' }}
          for “{{ store.fileSearch.query }}”
          <span v-if="store.fileSearch.truncated"> — showing the first results only, refine your search.</span>
        </p>
        <table class="files-page__table">
          <thead>
            <tr>
              <th class="files-page__th-name">Name</th>
              <th class="files-page__th-size">Size</th>
              <th class="files-page__th-modified">Modified</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entry in store.fileSearch.results"
              :key="entry.relativePath"
              class="files-page__row"
              :class="{ 'is-dir': entry.isDir }"
            >
              <td class="files-page__td-name">
                <button type="button" class="files-page__name-btn" @click="onSearchHitClick(entry)">
                  <svg v-if="entry.isDir" class="files-page__icon" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                    <path d="M2 3.5A1.5 1.5 0 013.5 2h2.5l1.5 2H11a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0111 13H3.5A1.5 1.5 0 012 11.5v-8z" />
                  </svg>
                  <svg v-else class="files-page__icon" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                    <path d="M3 1.5A0.5 0.5 0 013.5 1H8l3 3v8.5a0.5 0.5 0 01-0.5 0.5h-7A0.5 0.5 0 013 12.5v-11z" />
                    <path d="M8 1v3h3" />
                  </svg>
                  <span class="files-page__hit">
                    <span class="files-page__hit-name">{{ entry.name }}</span>
                    <span class="files-page__hit-path">{{ entry.parentPath || 'server' }}</span>
                  </span>
                </button>
              </td>
              <td class="files-page__td-size">{{ entry.isDir ? '—' : formatFileSize(entry.size) }}</td>
              <td class="files-page__td-modified">{{ formatModified(entry.updatedAt) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </Panel>

    <Panel v-else :padded="false">
      <div v-if="store.fileBrowser.loading" class="files-page__state">Loading…</div>
      <div v-else-if="store.fileBrowser.error" class="files-page__state files-page__state--error">{{ store.fileBrowser.error }}</div>
      <div v-else-if="!store.fileBrowser.entries.length" class="files-page__state">This folder is empty.</div>
      <table v-else class="files-page__table">
        <thead>
          <tr>
            <th class="files-page__th-name">Name</th>
            <th class="files-page__th-size">Size</th>
            <th class="files-page__th-modified">Modified</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in store.fileBrowser.entries"
            :key="entry.relativePath || entry.name"
            class="files-page__row"
            :class="{ 'is-dir': entry.isDir }"
            @dblclick="store.enterFileEntry(entry)"
          >
            <td class="files-page__td-name">
              <button
                v-if="entry.isDir"
                type="button"
                class="files-page__name-btn"
                @click="store.enterFileEntry(entry)"
              >
                <svg class="files-page__icon" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M2 3.5A1.5 1.5 0 013.5 2h2.5l1.5 2H11a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0111 13H3.5A1.5 1.5 0 012 11.5v-8z" />
                </svg>
                <span>{{ entry.name }}</span>
              </button>
              <button
                v-else
                type="button"
                class="files-page__name-btn"
                @click="onFileClick(entry)"
              >
                <svg class="files-page__icon" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M3 1.5A0.5 0.5 0 013.5 1H8l3 3v8.5a0.5 0.5 0 01-0.5 0.5h-7A0.5 0.5 0 013 12.5v-11z" />
                  <path d="M8 1v3h3" />
                </svg>
                <span>{{ entry.name }}</span>
              </button>
            </td>
            <td class="files-page__td-size">{{ formatFileSize(entry.size) }}</td>
            <td class="files-page__td-modified">{{ formatModified(entry.updatedAt) }}</td>
          </tr>
        </tbody>
      </table>
    </Panel>

    <Panel
      v-if="store.fileEditor.path || store.fileEditor.loading"
      ref="editorRef"
      :title="(store.fileEditor.path || 'Loading…') + (store.hasFileChanges ? ' •' : '')"
    >
      <template #action>
        <div class="files-page__editor-actions">
          <AppButton
            variant="ghost"
            size="sm"
            :disabled="store.fileEditor.saving"
            @click="onCloseEditor"
          >Close</AppButton>
          <AppButton
            variant="primary"
            size="sm"
            :loading="store.fileEditor.saving"
            :disabled="store.fileEditor.loading || !store.hasFileChanges"
            @click="onSave"
          >Save</AppButton>
        </div>
      </template>

      <div v-if="store.fileEditor.loading" class="files-page__state">Loading file…</div>
      <div v-else>
        <CodeEditor
          ref="codeEditorRef"
          v-model="store.fileEditor.content"
          :path="store.fileEditor.path"
          :disabled="store.fileEditor.saving"
          @save="onSave"
          @validity="onValidity"
        />
        <p v-if="store.fileEditor.error" class="files-page__editor-error">{{ store.fileEditor.error }}</p>
      </div>
    </Panel>

    <ConfirmModal
      :show="showDiscardConfirm"
      title="Discard unsaved changes?"
      message="You have unsaved changes."
      description="Continuing will discard your edits. This cannot be undone."
      type="warning"
      confirm-text="Discard changes"
      cancel-text="Keep editing"
      @confirm="handleDiscardConfirm"
      @cancel="handleDiscardCancel"
    />

    <ConfirmModal
      :show="showInvalidSaveConfirm"
      title="Save file with syntax errors?"
      message="This file has syntax errors."
      description="Saving an invalid config may prevent the server from starting. Save anyway?"
      type="warning"
      confirm-text="Save anyway"
      cancel-text="Keep editing"
      @confirm="handleInvalidSaveConfirm"
      @cancel="handleInvalidSaveCancel"
    />
  </div>
</template>

<style scoped>
.files-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.files-page__toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.files-page__location {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.files-page__location-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: transparent;
  padding: 0;
}

.files-page__location-copy {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-xs);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.files-page__location-copy:hover {
  background: var(--secondary-hover);
  color: var(--text-secondary);
}

.files-page__location-copy.is-copied {
  color: var(--success);
  border-color: var(--success);
}

.files-page__location-copy.is-error {
  color: var(--danger);
  border-color: var(--danger);
}

.files-page__crumbs {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-muted);
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}

.files-page__crumb {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-sm);
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.files-page__crumb:hover:not(.is-current) {
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.files-page__crumb.is-current {
  color: var(--text-primary);
  cursor: default;
}

.files-page__crumb-sep {
  color: var(--text-disabled);
}

.files-page__search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-2);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-disabled);
  flex-shrink: 0;
}

.files-page__search:focus-within {
  border-color: var(--primary);
}

.files-page__search-icon {
  flex-shrink: 0;
}

.files-page__search-input {
  background: transparent;
  border: none;
  outline: none;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--space-2) 0;
  width: 180px;
}

.files-page__search-input::placeholder {
  color: var(--text-disabled);
}

/* The native search-field clear affordance duplicates our own button. */
.files-page__search-input::-webkit-search-cancel-button {
  appearance: none;
}

.files-page__search-clear {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: var(--text-md);
  line-height: 1;
  padding: 0 2px;
  cursor: pointer;
}

.files-page__search-clear:hover {
  color: var(--text-primary);
}

.files-page__search-summary {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-color);
}

.files-page__hit {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.files-page__hit-path {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  font-family: var(--font-mono);
}

.files-page__state {
  padding: var(--space-5) var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.files-page__state--error {
  color: var(--danger);
}

.files-page__table {
  width: 100%;
  border-collapse: collapse;
}

.files-page__table thead th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-disabled);
  border-bottom: 1px solid var(--border-color);
}

.files-page__th-size,
.files-page__th-modified {
  width: 160px;
}

.files-page__row {
  border-bottom: 1px solid var(--border-color);
  transition: background 0.15s ease;
}

.files-page__row:last-child {
  border-bottom: none;
}

.files-page__row:hover {
  background: var(--bg-tertiary);
}

.files-page__row td {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  vertical-align: middle;
}

.files-page__td-size,
.files-page__td-modified {
  color: var(--text-disabled);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.files-page__name-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: transparent;
  border: none;
  font: inherit;
  color: inherit;
  text-align: left;
  padding: 0;
}

.files-page__name-btn {
  cursor: pointer;
  color: var(--text-secondary);
}

.files-page__name-btn:hover {
  color: var(--text-primary);
}

.files-page__name-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.files-page__row.is-dir .files-page__icon {
  color: var(--primary);
}

.files-page__row:not(.is-dir) .files-page__icon {
  color: var(--text-disabled);
}

.files-page__editor-actions {
  display: flex;
  gap: var(--space-2);
}

.files-page__editor-error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  color: var(--danger);
}
/* Mobile: the toolbar is Up / breadcrumbs / search / Refresh — four things
   that need more than a phone's width. Breadcrumbs get their own scrolling row
   (a deep path is long by nature and must stay legible), and the search grows
   into the row it shares with the two buttons. */
@media (max-width: 768px) {
  .files-page__toolbar {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }

  .files-page__crumbs {
    order: -1;
    flex: 1 0 100%;
    overflow-x: auto;
    /* Overrides the desktop clip: scrolling to the current folder beats
       truncating the path to its first segment. */
    white-space: nowrap;
  }

  .files-page__search {
    flex: 1;
    min-width: 0;
  }

  .files-page__search-input {
    width: 100%;
    min-width: 0;
  }

  /* Size and Modified are reference detail, not what you navigate by; the name
     column is what has to stay readable. Both are recoverable by rotating. */
  .files-page__th-size,
  .files-page__td-size,
  .files-page__th-modified,
  .files-page__td-modified {
    display: none;
  }
}
</style>
