<script setup>
import { computed } from 'vue'
import StatCard from '../ui/StatCard.vue'
import { formatFileSize, formatTimestamp } from '../../utils/format'

const props = defineProps({
  summary: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const totalCount = computed(() => props.summary?.total_snapshots ?? 0)
const totalBytes = computed(() => {
  const bytes = props.summary?.total_size_bytes
  if (typeof bytes !== 'number') return '—'
  return formatFileSize(bytes)
})
const lastSnapshotLabel = computed(() => {
  const last = props.summary?.last_snapshot
  if (!last?.createdAt) return '—'
  return formatTimestamp(last.createdAt)
})
const nextRunLabel = computed(() => {
  const next = props.summary?.next_run?.next_run_time
  if (!next) return '—'
  return formatTimestamp(next)
})
</script>

<template>
  <section class="stats-strip">
    <StatCard label="Snapshots" :value="totalCount" :accent="totalCount > 0 ? 'primary' : 'default'" />
    <StatCard label="Total size" :value="totalBytes" />
    <StatCard label="Last snapshot" :value="lastSnapshotLabel" />
    <StatCard label="Next scheduled" :value="nextRunLabel" :accent="props.summary?.next_run ? 'success' : 'default'" />
  </section>
</template>

<style scoped>
.stats-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  min-width: 0;
}

.stats-strip :deep(.stat-card__value) {
  font-size: var(--text-md);
}

@media (max-width: 900px) {
  .stats-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
