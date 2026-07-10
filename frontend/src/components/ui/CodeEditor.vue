<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { EditorView, keymap } from '@codemirror/view'
import { EditorState, Compartment, Prec } from '@codemirror/state'
import { basicSetup } from 'codemirror'
import {
  StreamLanguage,
  syntaxTree,
  HighlightStyle,
  syntaxHighlighting,
} from '@codemirror/language'
import { linter } from '@codemirror/lint'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { yaml } from '@codemirror/lang-yaml'
import { properties } from '@codemirror/legacy-modes/mode/properties'
import { toml } from '@codemirror/legacy-modes/mode/toml'
import { tags as t } from '@lezer/highlight'

const props = defineProps({
  modelValue: { type: String, default: '' },
  path: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'save', 'validity'])

const hostRef = ref(null)
let view = null

const languageCompartment = new Compartment()
const editableCompartment = new Compartment()

// ---------- Language selection ----------
// Extension → CodeMirror language extension. Mirrors TEXT_FILE_EXTENSIONS in the
// server store; anything unmapped (txt, log, md, …) renders as plaintext.
function languageForPath(path) {
  const ext = (path || '').toLowerCase().split('.').pop() || ''
  switch (ext) {
    case 'json':
      return json()
    case 'yml':
    case 'yaml':
      return yaml()
    case 'properties':
    case 'cfg':
    case 'conf':
      return StreamLanguage.define(properties)
    case 'toml':
      return StreamLanguage.define(toml)
    default:
      return []
  }
}

// ---------- Theme ----------
// Maps CodeMirror surfaces onto the app's CSS variables (see assets/global.css)
// so the editor matches the dark UI without hardcoded colors.
const appTheme = EditorView.theme(
  {
    '&': {
      color: 'var(--text-primary)',
      backgroundColor: 'var(--bg-primary)',
      fontSize: 'var(--text-sm)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-sm)',
    },
    '&.cm-focused': { outline: 'none', borderColor: 'var(--primary)' },
    '.cm-scroller': {
      fontFamily: 'var(--font-mono)',
      lineHeight: 'var(--leading-normal)',
      minHeight: '320px',
      maxHeight: '60vh',
    },
    '.cm-content': { caretColor: 'var(--primary)' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--primary)' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
      { backgroundColor: 'var(--secondary-hover)' },
    '.cm-activeLine': { backgroundColor: 'rgba(249, 115, 22, 0.06)' },
    '.cm-gutters': {
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-disabled)',
      border: 'none',
      borderRight: '1px solid var(--border-color)',
    },
    '.cm-activeLineGutter': {
      backgroundColor: 'var(--bg-tertiary)',
      color: 'var(--text-muted)',
    },
    '.cm-panels': {
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-secondary)',
    },
    '.cm-panels .cm-textfield': {
      backgroundColor: 'var(--bg-primary)',
      color: 'var(--text-primary)',
      border: '1px solid var(--border-color)',
    },
    '.cm-searchMatch': { backgroundColor: 'rgba(249, 115, 22, 0.25)' },
    '.cm-searchMatch.cm-searchMatch-selected': {
      backgroundColor: 'rgba(249, 115, 22, 0.5)',
    },
  },
  { dark: true }
)

const highlightStyle = HighlightStyle.define([
  { tag: t.comment, color: 'var(--text-disabled)', fontStyle: 'italic' },
  { tag: [t.keyword, t.operatorKeyword, t.modifier], color: 'var(--primary)' },
  { tag: [t.string, t.special(t.string)], color: 'var(--success)' },
  { tag: [t.number, t.bool, t.null], color: 'var(--warning)' },
  { tag: [t.propertyName, t.definition(t.propertyName)], color: 'var(--info)' },
  { tag: [t.name, t.variableName], color: 'var(--text-primary)' },
  { tag: [t.punctuation, t.separator, t.bracket], color: 'var(--text-muted)' },
  { tag: t.invalid, color: 'var(--danger)' },
])

// ---------- Validation ----------
// Generic Lezer error-node linter: flags any parse-error node so YAML (and any
// tree-based language) gets syntax diagnostics with no extra parser dependency.
function syntaxTreeLinter(vw) {
  const diagnostics = []
  syntaxTree(vw.state).cursor().iterate((node) => {
    if (node.type.isError) {
      diagnostics.push({
        from: node.from,
        to: node.to === node.from ? node.to + 1 : node.to,
        severity: 'error',
        message: 'Syntax error',
      })
    }
  })
  return diagnostics
}

const jsonLinter = jsonParseLinter()

function combinedLinter(vw) {
  const ext = (props.path || '').toLowerCase().split('.').pop() || ''
  // JSON has a dedicated linter with precise messages; everything else that has
  // a syntax tree (YAML, properties, toml) uses the generic error-node walk.
  const diagnostics = ext === 'json' ? jsonLinter(vw) : syntaxTreeLinter(vw)
  // Emit validity from the same pass that produced the diagnostics so the page
  // can gate saves without a stale read of the lint state field.
  emit('validity', { hasErrors: diagnostics.some((d) => d.severity === 'error') })
  return diagnostics
}

const saveKeymap = Prec.highest(
  keymap.of([
    {
      key: 'Mod-s',
      preventDefault: true,
      run: () => {
        emit('save')
        return true
      },
    },
  ])
)

function buildExtensions() {
  return [
    saveKeymap,
    basicSetup,
    languageCompartment.of(languageForPath(props.path)),
    editableCompartment.of(EditorView.editable.of(!props.disabled)),
    appTheme,
    syntaxHighlighting(highlightStyle),
    linter(combinedLinter),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        emit('update:modelValue', update.state.doc.toString())
      }
    }),
  ]
}

onMounted(() => {
  view = new EditorView({
    parent: hostRef.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: buildExtensions(),
    }),
  })
})

onUnmounted(() => {
  view?.destroy()
  view = null
})

// External content changes (opening a different file) replace the whole doc.
// Skip when the incoming value already matches to avoid clobbering the cursor
// during local typing (which round-trips through update:modelValue).
watch(
  () => props.modelValue,
  (value) => {
    if (!view) return
    const current = view.state.doc.toString()
    if (value === current) return
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value ?? '' },
    })
  }
)

watch(
  () => props.path,
  () => {
    if (!view) return
    view.dispatch({
      effects: languageCompartment.reconfigure(languageForPath(props.path)),
    })
  }
)

watch(
  () => props.disabled,
  (disabled) => {
    if (!view) return
    view.dispatch({
      effects: editableCompartment.reconfigure(
        EditorView.editable.of(!disabled)
      ),
    })
  }
)
</script>

<template>
  <div ref="hostRef" class="code-editor"></div>
</template>

<style scoped>
.code-editor {
  width: 100%;
}

.code-editor :deep(.cm-editor) {
  width: 100%;
}
</style>
