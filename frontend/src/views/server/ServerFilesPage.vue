<script setup>
import { computed, defineAsyncComponent, nextTick, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppButton from '../../components/ui/AppButton.vue'
import Panel from '../../components/ui/Panel.vue'
import FileTree from '../../components/files/FileTree.vue'
import ConfirmModal from '../../components/modals/ConfirmModal.vue'
import { formatFileSize } from '../../utils/format'
import { copyToClipboard } from '../../utils/clipboard'
import { useServerStore } from '../../stores/server'
import { useToast } from '../../composables/useToast'
import { t } from '../../i18n'

// Async-loaded so CodeMirror lands in its own chunk instead of the main bundle
// (the Files route is imported statically by the router).
const CodeEditor = defineAsyncComponent(() => import('../../components/ui/CodeEditor.vue'))

const store = useServerStore()
const toast = useToast()

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
  const crumbs = [{ label: t('files.root'), path: '' }]
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

// Opening a file switches the page into a two-pane workspace: folders move to a
// tree on the left, the editor takes the rest. Closing the file returns to the
// full-width browser.
const isEditing = computed(() => Boolean(store.fileEditor.path) || store.fileEditor.loading)

// The tree emits raw entries, same as the table rows, so both funnel through
// the one path that checks for unsaved changes first.
const onTreeSelect = (entry) => onFileClick(entry)

// ---------- File operations (#73) ----------
// Every entry point uploads into whichever folder the browser is showing, so
// none of them carry a destination of their own.

const fileInputRef = ref(null)
const openFilePicker = () => fileInputRef.value?.click()

const onFilesChosen = (event) => {
  runUpload(event.target.files)
  // Reset so picking the same file twice in a row still fires `change`.
  event.target.value = ''
}

// Files the backend refused because that name is already taken, held between
// the two halves of the replace prompt.
const pendingReplace = ref([])
const showReplaceConfirm = ref(false)

const replaceMessage = computed(() => {
  const count = pendingReplace.value.length
  if (count === 1) return t('files.replace.existsOne', { name: pendingReplace.value[0].name })
  return t('files.replace.existsMany', count)
})

const runUpload = async (files) => {
  const { conflicts } = await store.uploadFiles(files)
  if (conflicts.length) {
    pendingReplace.value = conflicts
    showReplaceConfirm.value = true
  }
}

const handleReplaceConfirm = async () => {
  const files = pendingReplace.value
  showReplaceConfirm.value = false
  pendingReplace.value = []
  await store.uploadFiles(files, { overwrite: true })
}

const handleReplaceCancel = () => {
  const skipped = pendingReplace.value.length
  showReplaceConfirm.value = false
  pendingReplace.value = []
  // The rows for these were dropped with the prompt, so say what happened or
  // the files would just silently not be there.
  if (skipped) {
    toast.info(t('files.uploadSkipped', skipped), t('nav.files'))
  }
}

// dragenter/dragleave fire again for every child element the pointer crosses,
// so a plain boolean flickers as the cursor moves over rows. Count instead.
const dragDepth = ref(0)
const isDragging = computed(() => dragDepth.value > 0)

const isFileDrag = (event) => Array.from(event.dataTransfer?.types || []).includes('Files')

const onDragEnter = (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault()
  dragDepth.value += 1
}

const onDragOver = (event) => {
  if (!isFileDrag(event)) return
  // Without this the browser leaves the page to open the dropped file.
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

const onDragLeave = () => {
  if (dragDepth.value > 0) dragDepth.value -= 1
}

const onDrop = (event) => {
  if (!isFileDrag(event)) return
  event.preventDefault()
  dragDepth.value = 0

  // A dropped folder shows up in `files` as a zero-byte entry that would upload
  // as an empty file of the same name. Skip those and say so, rather than
  // silently producing junk — recursive folder upload isn't wired up yet.
  const items = Array.from(event.dataTransfer.items || [])
  const dropped = Array.from(event.dataTransfer.files || [])
  const files = dropped.filter((_, i) => !items[i]?.webkitGetAsEntry?.()?.isDirectory)

  if (files.length < dropped.length) {
    toast.error(t('files.foldersUnsupported'), t('nav.files'))
  }
  if (files.length) runUpload(files)
}

// Delete runs in two passes for folders: the backend refuses a non-empty one
// unless `recursive` is set, which is what stops a stray click taking out a
// world that took months to build.
const pendingDelete = ref([])
const showDeleteConfirm = ref(false)
const recursiveTargets = ref([])
const showRecursiveConfirm = ref(false)
const deleting = ref(false)

const deleteMessage = computed(() => {
  const entry = pendingDelete.value[0]
  return entry ? t('files.delete.message', { name: entry.name }) : t('files.delete.messageFallback')
})

const deleteDescription = computed(() => {
  const entry = pendingDelete.value[0]
  if (!entry) return ''
  // Nothing about contents here — a folder with anything in it comes back from
  // the backend for a second, explicit confirm, and promising the recursive
  // delete up front would make that escalation read as a stutter.
  return entry.isDir ? t('files.delete.folderDescription') : t('files.delete.fileDescription')
})

const onDeleteClick = (entry) => {
  pendingDelete.value = [entry]
  showDeleteConfirm.value = true
}

const handleDeleteConfirm = async () => {
  const paths = pendingDelete.value.map((entry) => entry.relativePath || entry.name)
  deleting.value = true
  const { needsRecursive } = await store.deleteFileEntries(paths)
  deleting.value = false
  showDeleteConfirm.value = false
  pendingDelete.value = []

  if (needsRecursive.length) {
    recursiveTargets.value = needsRecursive
    showRecursiveConfirm.value = true
  }
}

const handleDeleteCancel = () => {
  showDeleteConfirm.value = false
  pendingDelete.value = []
}

const recursiveMessage = computed(() => {
  const targets = recursiveTargets.value
  return targets.length === 1
    ? t('files.delete.notEmptyOne', { name: targets[0] })
    : t('files.delete.notEmptyMany', targets.length)
})

const handleRecursiveConfirm = async () => {
  const paths = recursiveTargets.value
  deleting.value = true
  await store.deleteFileEntries(paths, { recursive: true })
  deleting.value = false
  showRecursiveConfirm.value = false
  recursiveTargets.value = []
}

const handleRecursiveCancel = () => {
  showRecursiveConfirm.value = false
  recursiveTargets.value = []
}

const showNewFolder = ref(false)
const newFolderName = ref('')
const creatingFolder = ref(false)

const openNewFolder = () => {
  newFolderName.value = ''
  showNewFolder.value = true
}

const handleNewFolderConfirm = async () => {
  const name = newFolderName.value.trim()
  if (!name) return
  creatingFolder.value = true
  const ok = await store.createFolder(name)
  creatingFolder.value = false
  if (ok) {
    showNewFolder.value = false
    newFolderName.value = ''
  }
}

const handleNewFolderCancel = () => {
  showNewFolder.value = false
  newFolderName.value = ''
}

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
  <div class="files-page" :class="{ 'is-editing': isEditing }">
    <!-- A real element rather than a bare <template> so the two views are
         symmetric and each can carry its own entrance animation. It repeats the
         parent's column layout, which the wrapper would otherwise swallow. -->
    <!-- Browser chrome. Hidden while editing: the breadcrumb and Up button
         steer the flat listing, which the tree replaces. -->
    <div
      v-if="!isEditing"
      class="files-page__browser"
      :class="{ 'is-dragging': isDragging }"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
    <!-- Sits above the listing rather than replacing it, so the folder you are
         about to drop into stays readable underneath. -->
    <div v-if="isDragging" class="files-page__dropzone">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M12 16V4M12 4L7 9M12 4l5 5" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M4 16v2.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V16" stroke-linecap="round" />
      </svg>
      <p class="files-page__dropzone-text">
        <i18n-t keypath="files.dropToUpload">
          <template #path><strong>{{ store.fileBrowser.currentPath || $t('files.root') }}</strong></template>
        </i18n-t>
      </p>
    </div>
    <div v-if="store.fileBrowser.absolutePath" class="files-page__location">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
        <path d="M2 3.5A1.5 1.5 0 013.5 2h2.5l1.5 2H11a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0111 13H3.5A1.5 1.5 0 012 11.5v-8z" />
      </svg>
      <code class="files-page__location-path">{{ store.fileBrowser.absolutePath }}</code>
      <button
        type="button"
        class="files-page__location-copy"
        :class="{ 'is-copied': copyState === 'copied', 'is-error': copyState === 'error' }"
        :title="copyState === 'copied' ? $t('files.copiedPath') : $t('files.copyPath')"
        @click="onCopyPath"
      >
        <span v-if="copyState === 'copied'">{{ $t('common.copied') }}</span>
        <span v-else-if="copyState === 'error'">{{ $t('common.failed') }}</span>
        <span v-else>{{ $t('common.copy') }}</span>
      </button>
    </div>
    <div class="files-page__toolbar">
      <AppButton variant="ghost" size="sm" :disabled="!canGoUp" @click="store.goUpDirectory">{{ $t('files.up') }}</AppButton>
      <nav class="files-page__crumbs" :aria-label="$t('files.pathLabel')">
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
          :placeholder="$t('files.search.placeholder')"
          :aria-label="$t('files.search.label')"
          @keydown.enter.prevent="onSearchSubmit"
          @keydown.esc.prevent="onClearSearch"
        />
        <button
          v-if="searchInput"
          type="button"
          class="files-page__search-clear"
          :title="$t('files.search.clear')"
          @click="onClearSearch"
        >×</button>
      </div>
      <AppButton variant="ghost" size="sm" :loading="store.fileBrowser.loading" @click="onRefresh">{{ $t('common.refresh') }}</AppButton>
      <AppButton variant="ghost" size="sm" @click="openNewFolder">{{ $t('files.newFolder') }}</AppButton>
      <AppButton variant="primary" size="sm" @click="openFilePicker">{{ $t('files.upload') }}</AppButton>
      <input
        ref="fileInputRef"
        type="file"
        multiple
        class="files-page__file-input"
        aria-hidden="true"
        tabindex="-1"
        @change="onFilesChosen"
      />
    </div>

    <!-- Upload queue. Successful rows clear themselves; failures stay until
         dismissed so an error in a long list isn't missed. -->
    <ul v-if="store.fileUploads.length" class="files-page__uploads">
      <li
        v-for="row in store.fileUploads"
        :key="row.id"
        class="files-page__upload"
        :class="`is-${row.status}`"
      >
        <span class="files-page__upload-name">{{ row.name }}</span>
        <template v-if="row.status === 'uploading'">
          <span class="files-page__upload-track">
            <span
              class="files-page__upload-bar"
              :class="{ 'is-indeterminate': row.pct < 0 }"
              :style="row.pct < 0 ? {} : { width: `${row.pct}%` }"
            />
          </span>
          <span class="files-page__upload-pct">{{ row.pct < 0 ? '…' : `${row.pct}%` }}</span>
          <button type="button" class="files-page__upload-action" @click="store.cancelUpload(row.id)">{{ $t('common.cancel') }}</button>
        </template>
        <template v-else>
          <span class="files-page__upload-error">{{ row.error }}</span>
          <button type="button" class="files-page__upload-action" @click="store.clearFinishedUploads()">{{ $t('common.dismiss') }}</button>
        </template>
      </li>
    </ul>

    <Panel v-if="store.fileSearch.active" :padded="false">
      <div v-if="store.fileSearch.loading" class="files-page__state">{{ $t('files.search.searching') }}</div>
      <div v-else-if="store.fileSearch.error" class="files-page__state files-page__state--error">{{ store.fileSearch.error }}</div>
      <div v-else-if="!store.fileSearch.results.length" class="files-page__state">
        {{ $t('files.search.noMatches', { query: store.fileSearch.query }) }}
      </div>
      <template v-else>
        <p class="files-page__search-summary">
          {{ $t(
            store.fileSearch.truncated ? 'files.search.summaryTruncated' : 'files.search.summary',
            { query: store.fileSearch.query },
            store.fileSearch.results.length
          ) }}
        </p>
        <table class="files-page__table">
          <thead>
            <tr>
              <th class="files-page__th-name">{{ $t('files.columns.name') }}</th>
              <th class="files-page__th-size">{{ $t('files.columns.size') }}</th>
              <th class="files-page__th-modified">{{ $t('files.columns.modified') }}</th>
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
                    <span class="files-page__hit-path">{{ entry.parentPath || $t('files.root') }}</span>
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
      <div v-if="store.fileBrowser.loading" class="files-page__state">{{ $t('common.loading') }}</div>
      <div v-else-if="store.fileBrowser.error" class="files-page__state files-page__state--error">{{ store.fileBrowser.error }}</div>
      <div v-else-if="!store.fileBrowser.entries.length" class="files-page__state">{{ $t('files.empty') }}</div>
      <table v-else class="files-page__table">
        <thead>
          <tr>
            <th class="files-page__th-name">{{ $t('files.columns.name') }}</th>
            <th class="files-page__th-size">{{ $t('files.columns.size') }}</th>
            <th class="files-page__th-modified">{{ $t('files.columns.modified') }}</th>
            <th class="files-page__th-actions"><span class="files-page__visually-hidden">{{ $t('files.columns.actions') }}</span></th>
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
            <td class="files-page__td-actions">
              <button
                type="button"
                class="files-page__delete"
                :title="$t('files.delete.entry', { name: entry.name })"
                :aria-label="$t('files.delete.entry', { name: entry.name })"
                @click.stop="onDeleteClick(entry)"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M2.5 3.5h9" stroke-linecap="round" />
                  <path d="M5.5 3.5v-1a1 1 0 011-1h1a1 1 0 011 1v1" />
                  <path d="M3.7 3.5l.5 8a1 1 0 001 .95h3.6a1 1 0 001-.95l.5-8" />
                  <path d="M5.9 6v4M8.1 6v4" stroke-linecap="round" />
                </svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </Panel>
    </div>

    <div v-else class="files-page__workspace">
      <aside class="files-page__tree-pane">
        <FileTree :active-path="store.fileEditor.path || ''" @select="onTreeSelect" />
      </aside>

      <Panel
        ref="editorRef"
        class="files-page__editor-pane"
        :title="(store.fileEditor.path || $t('common.loading')) + (store.hasFileChanges ? ' •' : '')"
      >
      <template #action>
        <div class="files-page__editor-actions">
          <AppButton
            variant="ghost"
            size="sm"
            :disabled="store.fileEditor.saving"
            @click="onCloseEditor"
          >{{ $t('common.close') }}</AppButton>
          <AppButton
            variant="primary"
            size="sm"
            :loading="store.fileEditor.saving"
            :disabled="store.fileEditor.loading || !store.hasFileChanges"
            @click="onSave"
          >{{ $t('common.save') }}</AppButton>
        </div>
      </template>

        <div v-if="store.fileEditor.loading" class="files-page__state">{{ $t('files.loadingFile') }}</div>
        <div v-else class="files-page__editor-body">
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
    </div>

    <ConfirmModal
      :show="showDiscardConfirm"
      :title="$t('files.discard.title')"
      :message="$t('files.discard.message')"
      :description="$t('files.discard.description')"
      type="warning"
      :confirm-text="$t('files.discard.confirm')"
      :cancel-text="$t('common.keepEditing')"
      @confirm="handleDiscardConfirm"
      @cancel="handleDiscardCancel"
    />

    <ConfirmModal
      :show="showInvalidSaveConfirm"
      :title="$t('files.invalidSave.title')"
      :message="$t('files.invalidSave.message')"
      :description="$t('files.invalidSave.description')"
      type="warning"
      :confirm-text="$t('files.invalidSave.confirm')"
      :cancel-text="$t('common.keepEditing')"
      @confirm="handleInvalidSaveConfirm"
      @cancel="handleInvalidSaveCancel"
    />

    <ConfirmModal
      :show="showDeleteConfirm"
      :title="$t('files.delete.title')"
      :message="deleteMessage"
      :description="deleteDescription"
      type="danger"
      :confirm-text="$t('common.delete')"
      :loading="deleting"
      :loading-text="$t('common.deleting')"
      @confirm="handleDeleteConfirm"
      @cancel="handleDeleteCancel"
    />

    <!-- Second pass: the backend declined a non-empty folder, so the cost is
         spelled out before the recursive retry rather than in the first prompt,
         where it would cry wolf over every empty folder. -->
    <ConfirmModal
      :show="showRecursiveConfirm"
      :title="$t('files.delete.recursiveTitle')"
      :message="recursiveMessage"
      :description="$t('files.delete.recursiveDescription')"
      type="danger"
      :confirm-text="$t('files.delete.recursiveConfirm')"
      :loading="deleting"
      :loading-text="$t('common.deleting')"
      @confirm="handleRecursiveConfirm"
      @cancel="handleRecursiveCancel"
    />

    <ConfirmModal
      :show="showReplaceConfirm"
      :title="$t('files.replace.title')"
      :message="replaceMessage"
      :description="$t('files.replace.description')"
      type="warning"
      :confirm-text="$t('files.replace.confirm')"
      @confirm="handleReplaceConfirm"
      @cancel="handleReplaceCancel"
    />

    <ConfirmModal
      :show="showNewFolder"
      :title="$t('files.newFolder')"
      :message="$t('files.folder.message', { path: store.fileBrowser.currentPath || $t('files.root') })"
      type="info"
      :confirm-text="$t('common.create')"
      :loading="creatingFolder"
      :loading-text="$t('common.creating')"
      @confirm="handleNewFolderConfirm"
      @cancel="handleNewFolderCancel"
    >
      <template #extra>
        <input
          v-model="newFolderName"
          type="text"
          class="files-page__folder-input"
          :placeholder="$t('files.folder.name')"
          :aria-label="$t('files.folder.name')"
          @keydown.enter.prevent="handleNewFolderConfirm"
        />
      </template>
    </ConfirmModal>
  </div>
</template>

<style scoped>
.files-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* ---------- Editing: tree + editor, filling the viewport ---------- */

/* Only while editing. The browser view keeps its natural height so a short
   folder listing doesn't stretch to fill the page. */
.files-page.is-editing {
  flex: 1;
  min-height: 0;
}

/* Carries the column layout the parent applies to its own children, so wrapping
   the browser in an element did not change how its chrome and panels stack. */
.files-page__browser {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  /* Anchors the drag-and-drop overlay. */
  position: relative;
}

/* Opening or closing a file is the biggest layout change in the app and it is
   always something the user just did, so it gets an entrance rather than a
   hard cut. Enter only: with both views in flow, animating the outgoing one
   would leave the two stacked for the duration. */
.files-page__browser,
.files-page__workspace {
  animation: files-view-in 180ms ease-out both;
}

@keyframes files-view-in {
  from { opacity: 0; transform: translateY(3px); }
  to   { opacity: 1; transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  .files-page__browser,
  .files-page__workspace {
    animation: none;
  }
}

.files-page__workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  /* Fixed rail, editor takes the rest. minmax(0,1fr) rather than 1fr so a long
     unbroken line in the file can't blow the column out past the viewport. */
  grid-template-columns: 260px minmax(0, 1fr);
  gap: var(--space-3);
}

.files-page__tree-pane {
  min-height: 0;
  min-width: 0;
}

.files-page__editor-pane {
  min-height: 0;
  min-width: 0;
}

/* Panel is a flex column; its body has to be allowed to shrink before the
   editor inside it can size to the leftover space rather than overflowing. */
.files-page__editor-pane :deep(.panel__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.files-page__editor-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* Flex the whole way down rather than percentage heights: a percentage needs a
   definite parent height, which a flex item only sometimes has. */
.files-page__editor-body :deep(.code-editor) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.files-page__editor-body :deep(.cm-editor) {
  flex: 1;
  min-height: 0;
}

/* CodeMirror's own theme caps the scroller at 60vh and floors it at 320px,
   which is right for the stacked layout but fights a pane that should fill
   whatever height it is given. The extra class raises specificity above the
   generated theme rule. */
.files-page__editor-body :deep(.cm-editor .cm-scroller) {
  min-height: 0;
  max-height: none;
}

/* Too narrow for two panes side by side (matches the 768px breakpoint the rest
   of the chrome uses): stack them, and cap the tree so the editor still gets
   most of the screen. */
@media (max-width: 768px) {
  .files-page__workspace {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 12rem) minmax(0, 1fr);
  }
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

/* ---------- File operations (#73) ---------- */

/* Kept in the DOM and driven by the picker button — `display: none` would make
   it unfocusable in some browsers, and it never needs to be seen. */
.files-page__file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.files-page__visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.files-page__dropzone {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  /* The listing stays legible underneath, so you can see which folder you are
     dropping into. */
  background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
  border: 2px dashed var(--accent);
  border-radius: var(--radius-md);
  color: var(--accent);
  pointer-events: none;
}

.files-page__dropzone-text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.files-page__dropzone-text strong {
  color: var(--text-primary);
}

.files-page__uploads {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.files-page__upload {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
}

.files-page__upload.is-failed {
  border-color: var(--danger);
}

.files-page__upload-name {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.files-page__upload-track {
  flex: 1 1 auto;
  height: 4px;
  min-width: 4rem;
  overflow: hidden;
  background: var(--bg-tertiary);
  border-radius: 999px;
}

.files-page__upload-bar {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: inherit;
  transition: width 0.2s ease;
}

/* No Content-Length on the request (a stream, or a proxy that strips it) means
   no percentage to show — sweep instead of sitting at 0%. */
.files-page__upload-bar.is-indeterminate {
  width: 35%;
  animation: files-page-upload-sweep 1.1s ease-in-out infinite;
}

@keyframes files-page-upload-sweep {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(340%); }
}

@media (prefers-reduced-motion: reduce) {
  .files-page__upload-bar.is-indeterminate {
    width: 100%;
    animation: none;
  }
}

.files-page__upload-pct {
  flex: 0 0 auto;
  color: var(--text-disabled);
  font-variant-numeric: tabular-nums;
}

.files-page__upload-error {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--danger);
}

.files-page__upload-action {
  flex: 0 0 auto;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
}

.files-page__upload-action:hover {
  color: var(--text-primary);
}

.files-page__th-actions,
.files-page__td-actions {
  width: 44px;
  text-align: right;
}

.files-page__delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-1);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-disabled);
  cursor: pointer;
  /* Revealed on row hover so the listing stays calm, but never hidden from the
     keyboard — :focus-visible below brings it back for tab users. */
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.files-page__row:hover .files-page__delete,
.files-page__delete:focus-visible {
  opacity: 1;
}

.files-page__delete:hover {
  background: var(--bg-tertiary);
  color: var(--danger);
}

/* Touch has no hover, so the affordance would never appear. */
@media (hover: none) {
  .files-page__delete {
    opacity: 1;
  }
}

.files-page__folder-input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.files-page__folder-input:focus {
  outline: none;
  border-color: var(--accent);
}
</style>
