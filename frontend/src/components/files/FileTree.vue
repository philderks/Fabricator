<script setup>
import { computed, ref, watch } from 'vue'
import { browseServerFiles } from '../../api/servers'
import { useServerStore } from '../../stores/server'

const props = defineProps({
  // Relative path of the file currently open in the editor. Its ancestors are
  // expanded automatically so the tree always shows where you are.
  activePath: { type: String, default: '' }
})

const emit = defineEmits(['select'])

const store = useServerStore()

const ROOT = ''

// How long a cached listing is trusted on remount before a background
// revalidation is kicked off.
const STALE_AFTER_MS = 15_000

// Module-level, keyed by server. This component is torn down every time the
// editor closes — the workspace it lives in is a v-else branch — so without an
// out-of-component cache, reopening any file refetched the entire tree, one
// request per level, before anything could render.
const caches = new Map()

function cacheFor(serverId) {
  let entry = caches.get(serverId)
  if (!entry) {
    // Raw Map/Set: the refs below wrap these in reactive proxies, and writes
    // through a proxy land in the underlying object, so the data survives a
    // remount even though the proxy does not.
    entry = { children: new Map(), expanded: new Set(), loadedAt: 0 }
    caches.set(serverId, entry)
  }
  return entry
}

let cache = cacheFor(store.currentServerId)

// path -> entries. The browse endpoint serves one directory at a time, so the
// tree is assembled from many calls. Vue 3 tracks Map/Set mutation natively,
// so these can be mutated in place.
const childrenByPath = ref(cache.children)
const expanded = ref(cache.expanded)
const loadingPaths = ref(new Set())
const error = ref('')

const pathOf = (entry) => entry.relativePath || entry.name

async function ensureChildren(path, { force = false } = {}) {
  if (!store.currentServerId) return
  if (!force && (childrenByPath.value.has(path) || loadingPaths.value.has(path))) return
  loadingPaths.value.add(path)
  try {
    // The backend already sorts folders first, then by name.
    const data = await browseServerFiles(store.currentServerId, path ? { path } : {})
    childrenByPath.value.set(path, data.entries || [])
    cache.loadedAt = Date.now()
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Unable to load this folder'
  } finally {
    loadingPaths.value.delete(path)
  }
}

async function toggle(entry) {
  const path = pathOf(entry)
  if (expanded.value.has(path)) {
    expanded.value.delete(path)
    return
  }
  expanded.value.add(path)
  await ensureChildren(path)
}

// Rendered as one flat list with an indent per level rather than a recursive
// component: same visual result, and it keeps the DOM shallow enough that a
// deep folder doesn't nest hundreds of wrappers.
const nodes = computed(() => {
  const out = []
  const walk = (path, depth) => {
    const entries = childrenByPath.value.get(path)
    if (!entries) return
    for (const entry of entries) {
      const p = pathOf(entry)
      out.push({ entry, path: p, depth })
      if (entry.isDir && expanded.value.has(p)) walk(p, depth + 1)
    }
  }
  walk(ROOT, 0)
  return out
})

// Open every folder on the way down to the file. Each ancestor's path is
// already known from splitting the string, so there is nothing to serialize
// on — fetching them together turns one round-trip per level into one wait.
function reveal(path) {
  if (!path) return Promise.resolve()
  const parts = path.split('/').filter(Boolean)
  parts.pop() // the file itself is not a folder to expand
  const ancestors = []
  let acc = ''
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part
    ancestors.push(acc)
    expanded.value.add(acc)
  }
  return Promise.all(ancestors.map((p) => ensureChildren(p)))
}

async function refresh() {
  // Re-read the root and everything currently open, leaving the expanded set
  // alone so a refresh doesn't collapse the tree the user has arranged.
  const open = [ROOT, ...expanded.value]
  await Promise.all(open.map((p) => ensureChildren(p, { force: true })))
}

// The flat browser has just listed a folder to get here, so adopt that instead
// of asking the server for something already in memory.
function seedFromBrowser() {
  const browser = store.fileBrowser
  if (!browser || browser.loading || !browser.entries?.length) return
  const path = browser.currentPath || ROOT
  if (!childrenByPath.value.has(path)) childrenByPath.value.set(path, browser.entries)
}

function prime() {
  seedFromBrowser()
  ensureChildren(ROOT)
  // Cached folders paint immediately; if that cache has had time to drift,
  // re-read it in the background so the tree self-corrects without ever
  // showing a spinner over content it already has.
  if (cache.children.size && Date.now() - cache.loadedAt > STALE_AFTER_MS) refresh()
}

prime()
watch(() => props.activePath, (p) => reveal(p), { immediate: true })

// A different server means a different tree — swap to that server's cache
// rather than showing the previous server's folders.
watch(() => store.currentServerId, () => {
  cache = cacheFor(store.currentServerId)
  childrenByPath.value = cache.children
  expanded.value = cache.expanded
  loadingPaths.value.clear()
  prime()
})

defineExpose({ refresh })
</script>

<template>
  <div class="file-tree">
    <div class="file-tree__head">
      <span class="file-tree__title">Explorer</span>
      <button
        type="button"
        class="file-tree__refresh"
        title="Refresh tree"
        @click="refresh"
      >
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true">
          <path d="M12 7a5 5 0 1 1-1.5-3.5" />
          <path d="M12.5 1.5V4H10" />
        </svg>
      </button>
    </div>

    <div class="file-tree__body">
      <p v-if="error" class="file-tree__error">{{ error }}</p>
      <p v-else-if="!nodes.length && loadingPaths.size" class="file-tree__state">Loading…</p>
      <p v-else-if="!nodes.length" class="file-tree__state">This server has no files.</p>

      <button
        v-for="node in nodes"
        :key="node.path"
        type="button"
        class="file-tree__row"
        :class="{
          'is-dir': node.entry.isDir,
          'is-active': !node.entry.isDir && node.path === activePath
        }"
        :style="{ paddingLeft: `${8 + node.depth * 12}px` }"
        :title="node.path"
        @click="node.entry.isDir ? toggle(node.entry) : emit('select', node.entry)"
      >
        <!-- Twisty, folders only: files keep the same indent via a spacer so
             names stay on one vertical line. -->
        <svg
          v-if="node.entry.isDir"
          class="file-tree__twisty"
          :class="{ 'is-open': expanded.has(node.path) }"
          width="10" height="10" viewBox="0 0 10 10"
          fill="none" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path d="M3.5 1.5L7 5l-3.5 3.5" />
        </svg>
        <span v-else class="file-tree__twisty" aria-hidden="true"></span>

        <svg v-if="node.entry.isDir" class="file-tree__icon" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M2 3.5A1.5 1.5 0 013.5 2h2.5l1.5 2H11a1.5 1.5 0 011.5 1.5v6A1.5 1.5 0 0111 13H3.5A1.5 1.5 0 012 11.5v-8z" />
        </svg>
        <svg v-else class="file-tree__icon" width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M3 1.5A0.5 0.5 0 013.5 1H8l3 3v8.5a0.5 0.5 0 01-0.5 0.5h-7A0.5 0.5 0 013 12.5v-11z" />
          <path d="M8 1v3h3" />
        </svg>

        <span class="file-tree__name">{{ node.entry.name }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.file-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.file-tree__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-3);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.file-tree__title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.file-tree__refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.file-tree__refresh:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.file-tree__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--space-1) 0;
}

.file-tree__row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding-top: 3px;
  padding-bottom: 3px;
  padding-right: var(--space-2);
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-family: inherit;
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.file-tree__row:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.file-tree__row.is-active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.file-tree__row.is-active .file-tree__icon {
  color: var(--primary);
}

.file-tree__twisty {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.file-tree__twisty.is-open {
  transform: rotate(90deg);
}

.file-tree__icon {
  flex-shrink: 0;
}

.file-tree__name {
  /* The row never wraps: a long name is clipped rather than pushing the tree
     wider or spilling onto a second line and breaking the indent read. */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-tree__state,
.file-tree__error {
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.file-tree__error {
  color: var(--danger);
}

@media (prefers-reduced-motion: reduce) {
  .file-tree__twisty {
    transition: none;
  }
}
</style>
