<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  uuid: { type: String, default: null },
  offlineMode: { type: Boolean, default: false },
  size: { type: Number, default: 24 },
})

const imgFailed = ref(false)

watch(() => [props.uuid, props.name], () => { imgFailed.value = false })

const initial = computed(() => {
  const n = (props.name || '').trim()
  return n ? n[0].toUpperCase() : '?'
})

// mc-heads.net resolves both UUIDs and usernames; fall back to the name when
// we don't have a UUID yet (e.g. optimistically-added players).
const identifier = computed(() => props.uuid || (props.name || '').trim() || null)

const showImg = computed(() =>
  !!identifier.value && !props.offlineMode && !imgFailed.value
)

const src = computed(() =>
  identifier.value
    ? `https://mc-heads.net/avatar/${encodeURIComponent(identifier.value)}/${props.size}`
    : null
)
</script>

<template>
  <span
    class="player-avatar"
    :style="{ width: size + 'px', height: size + 'px' }"
    aria-hidden="true"
  >
    <img
      v-if="showImg"
      class="player-avatar__img"
      :src="src"
      :width="size"
      :height="size"
      alt=""
      @error="imgFailed = true"
    />
    <span v-else class="player-avatar__initial">{{ initial }}</span>
  </span>
</template>

<style scoped>
.player-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  overflow: hidden;
}
.player-avatar__img {
  width: 100%;
  height: 100%;
  display: block;
}
.player-avatar__initial {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--text-muted);
}
</style>
