<script setup>
import { computed, ref } from 'vue'
import { getServerFile, saveServerFile } from '../../api/servers'
import { useToast } from '../../composables/useToast'

const props = defineProps({
  serverId: {
    type: [String, Number],
    required: true
  },
  fileBrowser: {
    type: Object,
    required: true
  },
  formatFileSize: {
    type: Function,
    required: true
  }
})

const emit = defineEmits(['go-up', 'refresh', 'enter-entry'])
const toast = useToast()

const editingFile = ref(null)
const editorContent = ref('')
const editorLoading = ref(false)
const editorSaving = ref(false)
const editorError = ref(null)

const textExtensions = new Set(['txt', 'json', 'properties', 'yml', 'yaml', 'toml', 'cfg', 'conf', 'log', 'md'])

const hasChanges = computed(() => {
  if (!editingFile.value) {
    return false
  }
  return editorContent.value !== editingFile.value.content
})

const handleGoUp = () => emit('go-up')
const handleRefresh = () => emit('refresh')

const isTextFile = (path) => {
  if (!path || typeof path !== 'string') {
    return false
  }
  const segments = path.toLowerCase().split('.')
  const extension = segments.pop() || ''
  return textExtensions.has(extension)
}

const confirmDiscardChanges = () => {
  if (!hasChanges.value) {
    return true
  }
  if (typeof window === 'undefined') {
    return true
  }
  return window.confirm('Discard unsaved changes?')
}

const openFile = async (entry) => {
  if (entry.isDir) {
    emit('enter-entry', entry)
    return
  }

  const filePath = entry.relativePath || entry.path || entry.name

  if (!isTextFile(filePath)) {
    toast.error('Only supported text files can be edited', 'Files')
    return
  }

  if (!confirmDiscardChanges()) {
    return
  }

  editorLoading.value = true
  editorError.value = null
  editingFile.value = { path: filePath, content: '' }
  editorContent.value = ''

  try {
    const file = await getServerFile(props.serverId, filePath)
    editingFile.value = { path: file.path, content: file.content }
    editorContent.value = file.content
  } catch (error) {
    const message = error?.message || 'Unable to open file'
    editorError.value = message
    editingFile.value = null
    editorContent.value = ''
    toast.error(message, 'Files')
  } finally {
    editorLoading.value = false
  }
}

const saveFile = async () => {
  if (!editingFile.value || editorSaving.value) {
    return
  }

  editorSaving.value = true
  editorError.value = null
  try {
    await saveServerFile(props.serverId, editingFile.value.path, editorContent.value)
    editingFile.value = { ...editingFile.value, content: editorContent.value }
    toast.success('File saved', 'Files')
  } catch (error) {
    const message = error?.message || 'Failed to save file'
    editorError.value = message
    toast.error(message, 'Files')
  } finally {
    editorSaving.value = false
  }
}

const closeEditor = () => {
  if (!editingFile.value) {
    return
  }

  if (!confirmDiscardChanges()) {
    return
  }

  editingFile.value = null
  editorContent.value = ''
  editorError.value = null
}

const handleEnter = (entry) => {
  openFile(entry)
}
</script>

<template>
  <div class="files-tab">
    <div class="files-toolbar">
      <div class="files-toolbar-left">
        <button class="btn btn-secondary" :disabled="!fileBrowser.currentPath" @click="handleGoUp">
          Up
        </button>
        <button class="btn btn-secondary" @click="handleRefresh">
          Refresh
        </button>
      </div>
      <div class="path-display">/{{ fileBrowser.currentPath }}</div>
    </div>
    <div class="files-list" v-if="!fileBrowser.loading && !fileBrowser.error">
      <div
        v-for="entry in fileBrowser.entries"
        :key="entry.path"
        class="file-entry"
        @click="handleEnter(entry)"
      >
        <div class="file-info">
          <span class="file-name">{{ entry.relativePath }}</span>
          <span class="file-meta">{{ entry.isDir ? 'Folder' : formatFileSize(entry.size) }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="fileBrowser.loading" class="placeholder-state">
      <p>Loading files…</p>
    </div>
    <div v-else class="placeholder-state">
      <p>{{ fileBrowser.error }}</p>
    </div>

    <div v-if="editingFile" class="editor-panel">
      <div class="editor-header">
        <span class="editor-path">{{ editingFile.path }}</span>
        <div class="editor-actions">
          <button class="btn btn-secondary" @click="closeEditor" :disabled="editorSaving">
            Close
          </button>
          <button
            class="btn btn-primary"
            @click="saveFile"
            :disabled="editorSaving || editorLoading || !hasChanges"
          >
            {{ editorSaving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
      <div v-if="editorLoading" class="editor-loading">
        Loading file…
      </div>
      <textarea
        v-else
        v-model="editorContent"
        class="editor-textarea"
        :disabled="editorSaving"
        spellcheck="false"
      ></textarea>
      <p v-if="editorError" class="editor-error">{{ editorError }}</p>
    </div>
  </div>
</template>

<style scoped>
.files-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.files-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.files-toolbar-left {
  display: flex;
  gap: 0.5rem;
}

.path-display {
  font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
  color: var(--text-muted);
}

.files-list {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.file-entry {
  display: flex;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: background 0.2s;
}

.file-entry:last-child {
  border-bottom: none;
}

.file-entry:hover {
  background: var(--bg-tertiary);
}

.file-name {
  font-weight: 600;
}

.file-meta {
  font-size: 0.8125rem;
  color: var(--text-disabled);
}

.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 4rem 2rem;
  color: var(--text-muted);
}

.placeholder-state p {
  margin: 0;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 1rem;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.editor-path {
  font-family: 'Fira Code', monospace;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.editor-actions {
  display: flex;
  gap: 0.5rem;
}

.editor-textarea {
  width: 100%;
  min-height: 400px;
  padding: 1rem;
  background: var(--bg-primary);
  border: none;
  color: var(--text-primary);
  font-family: 'Fira Code', monospace;
  font-size: 0.875rem;
  line-height: 1.5;
  resize: vertical;
}

.editor-textarea:focus {
  outline: none;
}

.editor-loading {
  padding: 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.editor-error {
  margin: 0;
  padding: 0.5rem 1rem 1rem;
  color: var(--danger);
  font-size: 0.875rem;
}
</style>
