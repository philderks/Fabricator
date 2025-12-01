<script setup>
const props = defineProps({
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

const handleGoUp = () => emit('go-up')
const handleRefresh = () => emit('refresh')
const handleEnter = (entry) => emit('enter-entry', entry)
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
</style>
