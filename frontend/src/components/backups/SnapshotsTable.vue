<script setup>
import { computed } from 'vue'
import Panel from '../ui/Panel.vue'
import { formatFileSize } from '../../utils/format'
import { snapshotDownloadUrl } from '../../api/backups'

const props = defineProps({
  snapshots: {
    type: Array,
    default: () => []
  },
  configsById: {
    type: Object,
    default: () => ({})
  },
  serverId: {
    type: [String, Number],
    default: null
  },
  /** snapshotId currently in-flight for a restore/delete action. */
  busySnapshotId: {
    type: String,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['restore', 'delete'])

const hasRows = computed(() => props.snapshots.length > 0)

function configName(configId) {
  return props.configsById[configId]?.name || '—'
}

function formatTimestamp(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

function formatDuration(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '—'
  if (seconds < 1) return '<1s'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

function statusMeta(snap) {
  // Backend marks status as success | warning | error
  if (snap.status === 'error') return { dot: 'var(--danger)', label: 'Failed' }
  if (snap.status === 'warning') return { dot: 'var(--warning)', label: 'Warning' }
  return { dot: 'var(--success)', label: 'OK' }
}

function typeLabel(type) {
  if (type === 'safety') return 'Safety'
  if (type === 'restore') return 'Restore'
  return 'Backup'
}

function downloadHref(snap) {
  if (!props.serverId) return '#'
  return snapshotDownloadUrl(props.serverId, snap.id)
}
</script>

<template>
  <Panel :padded="false">
    <div v-if="props.loading && !hasRows" class="snapshots-table__state">Loading snapshots…</div>
    <div v-else-if="!hasRows" class="snapshots-table__state">No snapshots yet.</div>
    <table v-else class="snapshots-table">
      <thead>
        <tr>
          <th class="snapshots-table__th-status">Status</th>
          <th class="snapshots-table__th-name">Snapshot</th>
          <th class="snapshots-table__th-config">Config</th>
          <th class="snapshots-table__th-type">Type</th>
          <th class="snapshots-table__th-created">Created</th>
          <th class="snapshots-table__th-size">Size</th>
          <th class="snapshots-table__th-duration">Duration</th>
          <th class="snapshots-table__th-actions"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="snap in props.snapshots"
          :key="snap.id"
          class="snapshots-table__row"
          :class="{ 'is-busy': props.busySnapshotId === snap.id }"
        >
          <td class="snapshots-table__td-status">
            <span
              class="snapshots-table__dot"
              :style="{ background: statusMeta(snap).dot }"
              :title="statusMeta(snap).label"
              aria-hidden="true"
            ></span>
          </td>
          <td class="snapshots-table__td-name">
            <div class="snapshots-table__name">{{ snap.fileName || snap.id }}</div>
            <div v-if="snap.message" class="snapshots-table__msg" :title="snap.message">{{ snap.message }}</div>
          </td>
          <td class="snapshots-table__td-config">{{ configName(snap.configId) }}</td>
          <td class="snapshots-table__td-type">
            <span class="snapshots-table__type-pill" :class="`snapshots-table__type-pill--${snap.type}`">
              {{ typeLabel(snap.type) }}
            </span>
          </td>
          <td class="snapshots-table__td-created">{{ formatTimestamp(snap.createdAt) }}</td>
          <td class="snapshots-table__td-size">{{ formatFileSize(snap.sizeBytes) }}</td>
          <td class="snapshots-table__td-duration">{{ formatDuration(snap.durationSeconds) }}</td>
          <td class="snapshots-table__td-actions">
            <div class="snapshots-table__actions">
              <button
                type="button"
                class="snapshots-table__action"
                :disabled="props.busySnapshotId === snap.id"
                title="Restore"
                @click="emit('restore', snap)"
              >
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M2.5 7a4.5 4.5 0 109 0 4.5 4.5 0 00-7.5-3.5"/>
                  <path d="M2.5 1.5v2.5H5"/>
                </svg>
                <span>Restore</span>
              </button>
              <a
                class="snapshots-table__action"
                :href="downloadHref(snap)"
                :title="'Download ' + (snap.fileName || snap.id)"
                download
              >
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M7 1.5v8M3.5 6L7 9.5 10.5 6"/>
                  <path d="M2 12h10"/>
                </svg>
                <span>Download</span>
              </a>
              <button
                type="button"
                class="snapshots-table__action snapshots-table__action--danger"
                :disabled="props.busySnapshotId === snap.id"
                title="Delete"
                @click="emit('delete', snap)"
              >
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
                  <path d="M3 4h8M5.5 4V2.5h3V4M4 4l.5 8h5L10 4"/>
                </svg>
                <span>Delete</span>
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </Panel>
</template>

<style scoped>
.snapshots-table__state {
  padding: var(--space-5) var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.snapshots-table {
  width: 100%;
  border-collapse: collapse;
}

.snapshots-table thead th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-disabled);
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.snapshots-table__th-status   { width: 36px; }
.snapshots-table__th-config   { width: 160px; }
.snapshots-table__th-type     { width: 90px; }
.snapshots-table__th-created  { width: 170px; }
.snapshots-table__th-size     { width: 90px; }
.snapshots-table__th-duration { width: 90px; }
.snapshots-table__th-actions  { width: 1px; }

.snapshots-table__row {
  border-bottom: 1px solid var(--border-color);
  transition: background 0.15s ease;
}

.snapshots-table__row:last-child {
  border-bottom: none;
}

.snapshots-table__row:hover {
  background: var(--bg-tertiary);
}

.snapshots-table__row.is-busy {
  opacity: 0.6;
}

.snapshots-table__row td {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  vertical-align: middle;
}

.snapshots-table__td-config,
.snapshots-table__td-created,
.snapshots-table__td-size,
.snapshots-table__td-duration {
  color: var(--text-disabled);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.snapshots-table__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.snapshots-table__name {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 360px;
}

.snapshots-table__msg {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 360px;
}

.snapshots-table__type-pill {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
}

.snapshots-table__type-pill--safety {
  color: var(--warning);
  border-color: var(--warning-dark);
}

.snapshots-table__type-pill--restore {
  color: var(--info);
  border-color: var(--info);
}

.snapshots-table__type-pill--backup {
  color: var(--primary);
  border-color: var(--primary);
}

.snapshots-table__actions {
  display: flex;
  gap: var(--space-1);
  justify-content: flex-end;
  visibility: hidden;
}

.snapshots-table__row:hover .snapshots-table__actions,
.snapshots-table__row:focus-within .snapshots-table__actions {
  visibility: visible;
}

.snapshots-table__action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  font: inherit;
  font-size: var(--text-xs);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.snapshots-table__action:hover:not(:disabled) {
  background: var(--secondary-hover);
  color: var(--text-primary);
}

.snapshots-table__action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.snapshots-table__action--danger:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}

.snapshots-table__action svg {
  flex-shrink: 0;
}
</style>
