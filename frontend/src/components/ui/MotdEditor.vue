<script setup>
import { computed, ref } from 'vue'
import ServerListEntry from './ServerListEntry.vue'
import { MOTD_COLORS, MOTD_FORMATS, activeStyle, alignMotd, alignmentOf, applyStyle, wrapMotd } from '../../utils/motd'
import { t } from '../../i18n'

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
const toolbarEl = ref(null)

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

// Makes an edit from applyStyle or alignMotd: only the part that changes is
// replaced, and the selection lands where the edit says.
function commit(edit) {
  const el = textarea.value
  if (el.value.slice(edit.from, edit.to) !== edit.text) replaceRange(el, edit.from, edit.to, edit.text)
  el.focus()
  el.setSelectionRange(edit.selectionStart, edit.selectionEnd)
  trackCaret()
}

// Toggles a colour or format on the selected characters (or, with a caret, on
// what gets typed next), rewriting only the codes that touch the selection.
// See applyStyle for the rules.
function apply(code) {
  const el = textarea.value
  if (el) commit(applyStyle(el.value, el.selectionStart, el.selectionEnd, code))
}

// Aligns the line(s) the selection is on, as a word processor does.
function align(where) {
  const el = textarea.value
  if (el) commit(alignMotd(el.value, where, el.selectionStart, el.selectionEnd))
}

// Ctrl/⌘ + key, as in any text editor.
const SHORTCUTS = { b: 'l', i: 'o', u: 'n' }
const SHORTCUT_KEYS = Object.fromEntries(Object.entries(SHORTCUTS).map(([key, code]) => [code, key.toUpperCase()]))
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)

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

// The selection, so the toolbar can show what is on for it (or, with a caret,
// for the next typed character), like a word processor's toolbar does. A
// pressed button is one a click would turn off.
const selection = ref([0, 0])
function trackCaret() {
  const el = textarea.value
  if (el) selection.value = [el.selectionStart, el.selectionEnd]
}
const active = computed(() => activeStyle(props.modelValue, ...selection.value))
const alignment = computed(() => alignmentOf(props.modelValue, ...selection.value))

const overflows = computed(() => wrapMotd(props.modelValue).length > 2)

// ---------- Toolbar ----------
// One list, so arrow keys can walk it: the toolbar is a single Tab stop, as
// role="toolbar" promises, and Left/Right/Home/End move between its buttons.

const FORMAT_GLYPHS = { l: 'B', o: 'I', n: 'U', m: 'S', k: '▒' }
const ICONS = {
  reset: 'M2.5 3h7M6 3v8M9 8.5l3 3m0-3l-3 3',
  left: 'M2 3h10M2 7h6M2 11h10',
  center: 'M2 3h10M4 7h6M2 11h10',
  right: 'M2 3h10M6 7h6M2 11h10'
}

const toolbar = computed(() => {
  const swatches = MOTD_COLORS.map((color) => {
    const label = t(`properties.motd.colors.${color.name}`)
    return {
      key: color.code,
      swatch: true,
      background: color.hex,
      label,
      title: `${label} (§${color.code})`,
      pressed: active.value.color === color.code,
      run: () => apply(color.code)
    }
  })
  const formats = [...Object.entries(MOTD_FORMATS), ['r', 'reset']].map(([code, name]) => {
    const label = t(`properties.motd.formats.${name}`)
    const key = SHORTCUT_KEYS[code]
    return {
      key: code,
      name,
      label,
      glyph: FORMAT_GLYPHS[code],
      icon: ICONS[name],
      title: `${label} (§${code}${key ? `, ${isMac ? '⌘' : 'Ctrl+'}${key}` : ''})`,
      shortcut: key && `${isMac ? 'Meta' : 'Control'}+${key}`,
      // Clearing is an action, not a state.
      pressed: code === 'r' ? undefined : Boolean(active.value[name]),
      run: () => apply(code)
    }
  })
  const aligns = ['left', 'center', 'right'].map((where) => {
    const label = t(`properties.motd.align.${where}`)
    return { key: where, name: where, label, title: label, icon: ICONS[where], pressed: alignment.value === where, run: () => align(where) }
  })
  let index = 0
  return [...swatches, { key: 'd1' }, ...formats, { key: 'd2' }, ...aligns].map((item) =>
    item.run ? { ...item, index: index++ } : { ...item, divider: true }
  )
})

const focusIndex = ref(0)

// A keyboard press keeps focus on the button, so the next one is an arrow key
// away; a mouse click leaves it in the textarea to carry on typing.
function run(item, event) {
  const button = event.currentTarget
  item.run()
  if (event.detail === 0) button.focus()
}

function onToolbarKeydown(event) {
  const buttons = [...toolbarEl.value.querySelectorAll('button')]
  const current = buttons.indexOf(document.activeElement)
  const next = { ArrowRight: current + 1, ArrowLeft: current - 1, Home: 0, End: buttons.length - 1 }[event.key]
  if (current < 0 || next === undefined) return
  event.preventDefault()
  buttons[(next + buttons.length) % buttons.length].focus()
}
</script>

<template>
  <div class="motd-editor">
    <div
      ref="toolbarEl"
      class="motd-editor__toolbar"
      role="toolbar"
      :aria-label="$t('properties.motd.toolbar')"
      @keydown="onToolbarKeydown"
    >
      <template v-for="item in toolbar" :key="item.key">
        <span v-if="item.divider" class="motd-editor__divider" aria-hidden="true"></span>
        <button
          v-else
          type="button"
          :class="item.swatch
            ? ['motd-editor__swatch', { 'motd-editor__swatch--active': item.pressed }]
            : ['motd-editor__format', `motd-editor__format--${item.name}`, { 'motd-editor__format--active': item.pressed }]"
          :style="item.swatch ? { background: item.background } : null"
          :title="item.title"
          :aria-label="item.label"
          :aria-pressed="item.pressed"
          :aria-keyshortcuts="item.shortcut"
          :tabindex="item.index === focusIndex ? 0 : -1"
          :disabled="disabled"
          @mousedown.prevent
          @focus="focusIndex = item.index"
          @click="run(item, $event)"
        >
          <svg v-if="item.icon" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path :d="item.icon" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <template v-else-if="item.glyph">{{ item.glyph }}</template>
        </button>
      </template>
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

    <ServerListEntry :name="serverName" :motd="modelValue" :icon-url="iconUrl" :max-players="maxPlayers" />
    <p v-if="overflows" class="motd-editor__warning" role="status">{{ $t('properties.motd.overflow') }}</p>
  </div>
</template>

<style scoped>
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
  display: inline-flex;
  align-items: center;
  justify-content: center;
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

/* What is on for the selection — a click would turn it off. */
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

.motd-editor__warning {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--warning);
}
</style>
