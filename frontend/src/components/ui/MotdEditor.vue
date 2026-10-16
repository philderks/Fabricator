<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { MOTD_COLORS, MOTD_FORMATS, codesAt, colorHex, parseMotd, shadowHex } from '../../utils/motd'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  serverName: { type: String, default: '' },
  maxPlayers: { type: Number, default: 20 },
  iconUrl: { type: String, default: '' },
  // Forwarded from FormField's slot so its label and hint point at the textarea.
  id: { type: String, default: undefined },
  describedBy: { type: String, default: undefined }
})

const emit = defineEmits(['update:modelValue'])

const textarea = ref(null)

const FORMAT_GLYPHS = { l: 'B', o: 'I', n: 'U', m: 'S', k: '▒', r: 'R' }
const formats = [...Object.entries(MOTD_FORMATS), ['r', 'reset']].map(([code, name]) => ({ code, name, glyph: FORMAT_GLYPHS[code] }))

// No selection: drop the code at the caret. A selection gets wrapped, then the
// style that was active at its end is re-emitted so the text after it keeps
// looking the way it did.
function apply(code) {
  const el = textarea.value
  const value = props.modelValue ?? ''
  const start = el?.selectionStart ?? value.length
  const end = el?.selectionEnd ?? value.length
  const tag = `§${code}`
  const restore = start !== end && end < value.length ? `§r${codesAt(value, end)}` : ''
  emit('update:modelValue', value.slice(0, start) + tag + value.slice(start, end) + restore + value.slice(end))
  nextTick(() => {
    el?.focus()
    el?.setSelectionRange(start + tag.length, end + tag.length)
  })
}

// The server list only ever shows two lines. Enter is refused on the second;
// a pasted third line is folded into it.
function onKeydown(event) {
  if (event.key === 'Enter' && (props.modelValue ?? '').includes('\n')) event.preventDefault()
}

function onInput(event) {
  const [first, ...rest] = event.target.value.replace(/\r/g, '').split('\n')
  emit('update:modelValue', rest.length ? `${first}\n${rest.join(' ')}` : first)
}

const lines = computed(() => parseMotd(props.modelValue))

// §k text re-rolls its characters ten times a second, as it does in-game. The
// timer only runs while there is some.
const tick = ref(0)
let timer = null
const hasObfuscated = computed(() => lines.value.some((line) => line.some((seg) => seg.style.obfuscated)))
watch(hasObfuscated, (on) => {
  clearInterval(timer)
  timer = on ? setInterval(() => { tick.value += 1 }, 100) : null
}, { immediate: true })
onUnmounted(() => clearInterval(timer))

const GLYPHS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
function segmentText(seg) {
  if (!seg.style.obfuscated) return seg.text
  void tick.value
  return seg.text.replace(/\S/g, () => GLYPHS[Math.floor(Math.random() * GLYPHS.length)])
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

const hasIcon = ref(false)
watch(() => props.iconUrl, () => { hasIcon.value = false })
</script>

<template>
  <div class="motd-editor">
    <div class="motd-editor__toolbar" role="toolbar" :aria-label="$t('properties.motd.toolbar')">
      <button
        v-for="color in MOTD_COLORS"
        :key="color.code"
        type="button"
        class="motd-editor__swatch"
        :style="{ background: color.hex }"
        :title="`${$t(`properties.motd.colors.${color.name}`)} (§${color.code})`"
        :aria-label="$t(`properties.motd.colors.${color.name}`)"
        :disabled="disabled"
        @mousedown.prevent
        @click="apply(color.code)"
      ></button>
      <span class="motd-editor__divider" aria-hidden="true"></span>
      <button
        v-for="format in formats"
        :key="format.code"
        type="button"
        class="motd-editor__format"
        :class="`motd-editor__format--${format.name}`"
        :title="`${$t(`properties.motd.formats.${format.name}`)} (§${format.code})`"
        :aria-label="$t(`properties.motd.formats.${format.name}`)"
        :disabled="disabled"
        @mousedown.prevent
        @click="apply(format.code)"
      >{{ format.glyph }}</button>
    </div>

    <textarea
      :id="id"
      ref="textarea"
      class="motd-editor__input"
      rows="2"
      spellcheck="false"
      :value="modelValue"
      :placeholder="$t('properties.identity.motdPlaceholder')"
      :disabled="disabled"
      :aria-describedby="describedBy"
      @keydown="onKeydown"
      @input="onInput"
    ></textarea>

    <!-- Drawn at the in-game size (GUI scale 2), so where a line is cut off
         here is where it is cut off in the server list. -->
    <div class="motd-editor__preview" role="img" :aria-label="$t('properties.motd.preview')">
      <div class="motd-editor__entry">
        <span class="motd-editor__icon">
          <img v-if="iconUrl" v-show="hasIcon" :src="iconUrl" alt="" @load="hasIcon = true" @error="hasIcon = false" />
          <span v-if="!hasIcon" aria-hidden="true">?</span>
        </span>
        <div class="motd-editor__text">
          <div class="motd-editor__row">
            <span class="motd-editor__name">{{ serverName || $t('servers.defaultName') }}</span>
            <span class="motd-editor__players">
              <span><span class="motd-editor__gray">0</span><span class="motd-editor__dark">/</span><span class="motd-editor__gray">{{ maxPlayers }}</span></span>
              <svg class="motd-editor__ping" width="20" height="16" viewBox="0 0 10 8" aria-hidden="true">
                <rect v-for="bar in 5" :key="bar" :x="(bar - 1) * 2" :y="8 - bar - 3" width="1" :height="bar + 3" fill="#00ff21" />
              </svg>
            </span>
          </div>
          <div v-for="(line, index) in lines" :key="index" class="motd-editor__line">
            <span v-for="(seg, segIndex) in line" :key="segIndex" :style="segmentStyle(seg)">{{ segmentText(seg) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* "Minecraft" by Jacob Debono (JDGraphics), Public Domain —
   https://www.fontspace.com/minecraft-font-f28180. Each face only downloads
   once the preview actually uses it. */
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

.motd-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.motd-editor__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.motd-editor__swatch,
.motd-editor__format {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: transform 120ms ease, border-color 120ms ease;
}

.motd-editor__swatch:hover:not(:disabled),
.motd-editor__format:hover:not(:disabled) {
  border-color: var(--primary);
  transform: translateY(-1px);
}

.motd-editor__swatch:focus-visible,
.motd-editor__format:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 1px;
}

.motd-editor__swatch:disabled,
.motd-editor__format:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.motd-editor__format {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: var(--text-sm);
}

.motd-editor__format--bold { font-weight: 700; }
.motd-editor__format--italic { font-style: italic; }
.motd-editor__format--underline { text-decoration: underline; }
.motd-editor__format--strikethrough { text-decoration: line-through; }

.motd-editor__divider {
  width: 1px;
  height: 18px;
  margin: 0 var(--space-1);
  background: var(--border-color);
}

.motd-editor__input {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  padding: 6px 10px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  resize: none;
}

.motd-editor__input:focus {
  outline: none;
  border-color: var(--primary);
}

.motd-editor__input:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

/* Scrolls rather than shrinks on narrow screens, so the clipping stays true. */
.motd-editor__preview {
  overflow-x: auto;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: #0b0b0b;
}

.motd-editor__entry {
  display: flex;
  gap: 6px;
  width: 610px;
  padding: 2px;
  border: 2px solid #808080;
  background: #000;
  font-family: 'Minecraft', var(--font-mono);
  font-size: 16px;
  line-height: 18px;
  white-space: pre;
  user-select: none;
}

.motd-editor__icon {
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

.motd-editor__icon img {
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.motd-editor__text {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}

.motd-editor__row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 4px;
}

.motd-editor__line {
  overflow: hidden;
  height: 18px;
}

.motd-editor__name {
  overflow: hidden;
  color: #fff;
  text-shadow: 2px 2px 0 #3f3f3f;
}

.motd-editor__players {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex-shrink: 0;
}

.motd-editor__gray {
  color: #aaa;
  text-shadow: 2px 2px 0 #2a2a2a;
}

.motd-editor__dark {
  color: #555;
  text-shadow: 2px 2px 0 #151515;
}

.motd-editor__ping {
  image-rendering: pixelated;
  shape-rendering: crispEdges;
}
</style>
