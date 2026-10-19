<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { MOTD_COLORS, MOTD_FORMATS, activeStyle, applyStyle, centerMotd, colorHex, glyphAdvance, shadowHex, wrapMotd } from '../../utils/motd'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  serverName: { type: String, default: '' },
  // A String while the Max Players input is cleared (v-model.number gives '').
  maxPlayers: { type: [Number, String], default: 20 },
  iconUrl: { type: String, default: '' },
  // Forwarded from FormField's slot so its label and hint point at the textarea.
  id: { type: String, default: undefined },
  describedBy: { type: String, default: undefined }
})

const emit = defineEmits(['update:modelValue'])

const textarea = ref(null)

const FORMAT_GLYPHS = { l: 'B', o: 'I', n: 'U', m: 'S', k: '▒', r: 'R' }
// Ctrl/⌘ + key, as in any text editor.
const SHORTCUTS = { b: 'l', i: 'o', u: 'n' }
const SHORTCUT_KEYS = Object.fromEntries(Object.entries(SHORTCUTS).map(([key, code]) => [code, key.toUpperCase()]))
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)
const formats = [...Object.entries(MOTD_FORMATS), ['r', 'reset']].map(([code, name]) => ({
  code,
  name,
  glyph: FORMAT_GLYPHS[code],
  shortcut: SHORTCUT_KEYS[code] && (isMac ? `⌘${SHORTCUT_KEYS[code]}` : `Ctrl+${SHORTCUT_KEYS[code]}`),
  ariaShortcut: SHORTCUT_KEYS[code] && `${isMac ? 'Meta' : 'Control'}+${SHORTCUT_KEYS[code]}`
}))

// Replaces start..end of the textarea through insertText, which keeps the edit
// on the browser's undo stack (assigning .value wipes it) and fires the input
// event that emits the new value.
function replaceRange(el, start, end, text) {
  el.focus()
  el.setSelectionRange(start, end)
  if (!document.execCommand('insertText', false, text)) {
    el.setRangeText(text, start, end, 'end')
    emit('update:modelValue', el.value)
  }
}

// Toggles a colour or format on the selected characters (or, with a caret, on
// what gets typed next), rewriting only the codes that touch the selection.
// See applyStyle for the rules.
function apply(code) {
  const el = textarea.value
  if (!el) return
  const edit = applyStyle(el.value, el.selectionStart, el.selectionEnd, code)
  if (el.value.slice(edit.from, edit.to) !== edit.text) replaceRange(el, edit.from, edit.to, edit.text)
  el.focus()
  el.setSelectionRange(edit.selectionStart, edit.selectionEnd)
  trackCaret()
}

function center() {
  const el = textarea.value
  if (!el) return
  const centered = centerMotd(el.value)
  if (centered !== el.value) replaceRange(el, 0, el.value.length, centered)
  trackCaret()
}

// The server list only ever shows two lines. Enter is refused once there are
// two, unless it replaces the line break itself; a pasted third line is folded
// into the second.
function onKeydown(event) {
  const shortcut = (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && SHORTCUTS[event.key.toLowerCase()]
  if (shortcut) {
    event.preventDefault()
    apply(shortcut)
    return
  }
  if (event.key !== 'Enter') return
  const { value, selectionStart, selectionEnd } = event.target
  if (value.includes('\n') && !value.slice(selectionStart, selectionEnd).includes('\n')) event.preventDefault()
}

// The selection, so the toolbar can show what is on for it (or, with a caret,
// for the next typed character), like a word processor's toolbar does. A
// pressed button is one a click would turn off.
const selection = ref([0, 0])
function trackCaret() {
  const el = textarea.value
  if (el) selection.value = [el.selectionStart, el.selectionEnd]
}
const active = computed(() => activeStyle(props.modelValue, ...selection.value))

function onInput(event) {
  const el = event.target
  const [first, ...rest] = el.value.split('\n')
  const value = rest.length ? `${first}\n${rest.join(' ')}` : first
  if (value !== el.value) {
    // Written back here rather than left to Vue, which would put the caret at
    // the end. Newlines became spaces, so the offsets still line up.
    const { selectionStart, selectionEnd } = el
    el.value = value
    el.setSelectionRange(selectionStart, selectionEnd)
  }
  emit('update:modelValue', value)
  trackCaret()
}

// Laid out with the game's own glyph widths rather than the preview font's,
// so the wrap, and whether anything falls past line two, match the client.
const wrapped = computed(() => wrapMotd(props.modelValue))
const lines = computed(() => wrapped.value.slice(0, 2))
const overflows = computed(() => wrapped.value.length > 2)

// §k text re-rolls its characters ten times a second, as it does in-game. The
// timer only runs while there is some, and not for viewers who asked for
// reduced motion.
const tick = ref(0)
let timer = null
const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const hasObfuscated = computed(() => lines.value.some((line) => line.some((seg) => seg.style.obfuscated)))
watch(hasObfuscated, (on) => {
  clearInterval(timer)
  timer = on && !reduceMotion ? setInterval(() => { tick.value += 1 }, 100) : null
}, { immediate: true })
onUnmounted(() => clearInterval(timer))

// Every glyph sits in a box exactly as wide as the game draws it (at GUI scale
// 2), so spacing and centring in the preview are the client's, not whatever
// the preview font's own metrics would make of them.
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
        :class="{ 'motd-editor__swatch--active': active.color === color.code }"
        :style="{ background: color.hex }"
        :title="`${$t(`properties.motd.colors.${color.name}`)} (§${color.code})`"
        :aria-label="$t(`properties.motd.colors.${color.name}`)"
        :aria-pressed="active.color === color.code"
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
        :class="[`motd-editor__format--${format.name}`, { 'motd-editor__format--active': active[format.name] }]"
        :title="`${$t(`properties.motd.formats.${format.name}`)} (§${format.code}${format.shortcut ? `, ${format.shortcut}` : ''})`"
        :aria-label="$t(`properties.motd.formats.${format.name}`)"
        :aria-pressed="format.code === 'r' ? undefined : Boolean(active[format.name])"
        :aria-keyshortcuts="format.ariaShortcut"
        :disabled="disabled"
        @mousedown.prevent
        @click="apply(format.code)"
      >{{ format.glyph }}</button>
      <span class="motd-editor__divider" aria-hidden="true"></span>
      <button
        type="button"
        class="motd-editor__format"
        :title="$t('properties.motd.center')"
        :aria-label="$t('properties.motd.center')"
        :disabled="disabled"
        @mousedown.prevent
        @click="center"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M2 3H12M4 7H10M2 11H12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </button>
    </div>

    <!-- Same shape as the server-list entry below: icon (if the page has one
         to offer) on the left, the two MOTD lines beside it. -->
    <div class="motd-editor__compose">
      <slot name="icon" />
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
        @select="trackCaret"
        @click="trackCaret"
        @keyup="trackCaret"
        @focus="trackCaret"
      ></textarea>
    </div>

    <!-- Drawn at the in-game size (GUI scale 2). The game word-wraps the MOTD
         to the text column and shows the first two lines, so this does too. -->
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
          <div v-for="(line, index) in glyphLines" :key="index" class="motd-editor__line">
            <span v-for="(part, partIndex) in line" :key="partIndex" :style="segmentStyle(part.seg)"><span
              v-for="(glyph, glyphIndex) in part.glyphs"
              :key="glyphIndex"
              class="motd-editor__glyph"
              :style="{ width: glyph.width }"
            >{{ glyphText(part.seg, glyph.ch) }}</span></span>
          </div>
        </div>
      </div>
    </div>
    <p v-if="overflows" class="motd-editor__warning" role="status">{{ $t('properties.motd.overflow') }}</p>
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

/* The colour or format the caret is in. */
.motd-editor__swatch--active {
  box-shadow: 0 0 0 2px var(--bg-primary), 0 0 0 4px var(--primary);
}

.motd-editor__format--active {
  border-color: var(--primary);
  color: var(--primary);
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

.motd-editor__compose {
  display: flex;
  gap: var(--space-3);
}

.motd-editor__input {
  flex: 1;
  min-width: 0;
  height: 64px;
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

/* MOTD_WIDTH (267 GUI px) at GUI scale 2. */
.motd-editor__text {
  width: 534px;
  padding-top: 2px;
}

.motd-editor__row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: 4px;
}

/* Lines arrive already wrapped; clipping only covers the preview font being a
   hair wider than the game's. */
.motd-editor__line {
  height: 18px;
  overflow: hidden;
}

/* Decoration doesn't propagate into inline-blocks, so each glyph takes it. */
.motd-editor__glyph {
  display: inline-block;
  text-decoration-line: inherit;
}

.motd-editor__warning {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--warning);
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
