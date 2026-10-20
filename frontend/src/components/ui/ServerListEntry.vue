<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { colorHex, glyphAdvance, shadowHex, wrapMotd } from '../../utils/motd'
import { t } from '../../i18n'

// A server as the Minecraft multiplayer list draws it, at GUI scale 2: icon,
// name, player count, ping and the MOTD's first two wrapped lines.
const props = defineProps({
  name: { type: String, default: '' },
  motd: { type: String, default: '' },
  iconUrl: { type: String, default: '' },
  players: { type: [Number, String], default: 0 },
  // A String while the Max Players input is cleared (v-model.number gives '').
  maxPlayers: { type: [Number, String], default: 20 }
})

const displayName = computed(() => props.name || t('servers.defaultName'))

// Laid out with the game's own glyph widths rather than the preview font's,
// so the wrap matches the client.
const lines = computed(() => wrapMotd(props.motd).slice(0, 2))

const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// §k text re-rolls its characters ten times a second, as it does in-game. The
// timer only runs while there is some, and not for viewers who asked for
// reduced motion.
const tick = ref(0)
let timer = null
const hasObfuscated = computed(() => lines.value.some((line) => line.some((seg) => seg.style.obfuscated)))
watch(hasObfuscated, (on) => {
  clearInterval(timer)
  timer = on && !reduceMotion ? setInterval(() => { tick.value += 1 }, 100) : null
}, { immediate: true })
onUnmounted(() => clearInterval(timer))

// Every glyph sits in a box exactly as wide as the game draws it, so spacing
// and alignment are the client's, not whatever the preview font's own metrics
// would make of them.
const glyphLines = computed(() => lines.value.map((line) => line.map((seg) => ({
  seg,
  glyphs: Array.from(seg.text, (ch) => ({ ch, width: `${glyphAdvance(ch, seg.style.bold) * 2}px` }))
}))))

const GLYPHS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
function glyphText(seg, ch) {
  if (!seg.style.obfuscated || ch === ' ') return ch
  void tick.value
  return GLYPHS[Math.floor(Math.random() * GLYPHS.length)]
}

function segmentStyle({ style }) {
  const hex = colorHex(style)
  const decoration = [style.underline && 'underline', style.strikethrough && 'line-through'].filter(Boolean).join(' ')
  return {
    color: hex,
    textShadow: `2px 2px 0 ${shadowHex(hex)}`,
    fontWeight: style.bold ? 700 : 400,
    fontStyle: style.italic ? 'italic' : 'normal',
    textDecorationLine: decoration || 'none'
  }
}

// The picture is decorative to a screen reader; this says what it shows.
const label = computed(() => {
  const motd = lines.value.map((line) => line.map((seg) => seg.text).join('').trim()).filter(Boolean).join(' ')
  const state = t('serverEntry.players', { online: props.players, max: props.maxPlayers })
  return [displayName.value, motd, state].filter(Boolean).join('. ')
})

const hasIcon = ref(false)
watch(() => props.iconUrl, () => { hasIcon.value = false })
</script>

<template>
  <!-- Scrolls rather than shrinks on narrow screens, so the layout stays true. -->
  <div class="server-entry" role="img" :aria-label="label">
    <div class="server-entry__row">
      <span class="server-entry__icon">
        <img v-if="iconUrl" v-show="hasIcon" :src="iconUrl" alt="" @load="hasIcon = true" @error="hasIcon = false" />
        <span v-if="!hasIcon" aria-hidden="true">?</span>
      </span>
      <div class="server-entry__text">
        <div class="server-entry__head">
          <span class="server-entry__name">{{ displayName }}</span>
          <span class="server-entry__status">
            <span><span class="server-entry__gray">{{ players }}</span><span class="server-entry__dark">/</span><span class="server-entry__gray">{{ maxPlayers }}</span></span>
            <svg class="server-entry__ping" width="20" height="16" viewBox="0 0 10 8" aria-hidden="true">
              <rect v-for="bar in 5" :key="bar" :x="(bar - 1) * 2" :y="8 - bar - 3" width="1" :height="bar + 3" />
            </svg>
          </span>
        </div>
        <div v-for="(line, index) in glyphLines" :key="index" class="server-entry__line">
          <span v-for="(part, partIndex) in line" :key="partIndex" :style="segmentStyle(part.seg)"><span
            v-for="(glyph, glyphIndex) in part.glyphs"
            :key="glyphIndex"
            class="server-entry__glyph"
            :style="{ width: glyph.width }"
          >{{ glyphText(part.seg, glyph.ch) }}</span></span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* "Minecraft" by Jacob Debono (JDGraphics), Public Domain —
   https://www.fontspace.com/minecraft-font-f28180. Each face only downloads
   once something actually uses it. */
@font-face {
  font-family: 'Minecraft';
  src: url('../../assets/fonts/minecraft/Minecraft-Regular.otf') format('opentype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: 'Minecraft';
  src: url('../../assets/fonts/minecraft/Minecraft-Bold.otf') format('opentype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: 'Minecraft';
  src: url('../../assets/fonts/minecraft/Minecraft-Italic.otf') format('opentype');
  font-weight: 400;
  font-style: italic;
  font-display: swap;
}

@font-face {
  font-family: 'Minecraft';
  src: url('../../assets/fonts/minecraft/Minecraft-BoldItalic.otf') format('opentype');
  font-weight: 700;
  font-style: italic;
  font-display: swap;
}

.server-entry {
  overflow-x: auto;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: #0b0b0b;
}

.server-entry__row {
  display: flex;
  gap: 6px;
  width: max-content;
  padding: 2px;
  border: 2px solid #808080;
  background: #000;
  font-family: 'Minecraft', var(--font-mono);
  /* One font pixel = 2px, the game's pixel at GUI scale 2. */
  font-size: 19.2px;
  line-height: 18px;
  white-space: pre;
  user-select: none;
}

.server-entry__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  background: #1f1f1f;
  color: #555;
  font-size: 32px;
}

.server-entry__icon img {
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

/* MOTD_WIDTH (267 GUI px) at GUI scale 2. */
.server-entry__text {
  width: 534px;
  padding-top: 2px;
}

.server-entry__head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 4px;
}

/* Lines arrive already wrapped; clipping only covers the preview font being a
   hair wider than the game's. */
.server-entry__line {
  height: 18px;
  overflow: hidden;
}

/* Decoration doesn't propagate into inline-blocks, so each glyph takes it. */
.server-entry__glyph {
  display: inline-block;
  text-decoration-line: inherit;
}

.server-entry__name {
  overflow: hidden;
  color: #fff;
  text-shadow: 2px 2px 0 #3f3f3f;
}

.server-entry__status {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex-shrink: 0;
}

.server-entry__gray {
  color: #aaa;
  text-shadow: 2px 2px 0 #2a2a2a;
}

.server-entry__dark {
  color: #555;
  text-shadow: 2px 2px 0 #151515;
}

.server-entry__ping {
  image-rendering: pixelated;
  shape-rendering: crispEdges;
  fill: #00ff21;
}
</style>
