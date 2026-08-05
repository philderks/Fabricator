<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import AppButton from '../../components/ui/AppButton.vue'
import { useServerStore } from '../../stores/server'

const store = useServerStore()

// Case-sensitive on purpose: Minecraft/Log4j and the JVM emit these tokens in
// uppercase (e.g. "[Server thread/WARN]", "WARNING:"), so matching only
// uppercase avoids false hits on ordinary words in chat/messages.
const LEVEL_PATTERN = /\b(FATAL|SEVERE|ERROR|WARNING|WARN|INFO|DEBUG|TRACE)\b/

// Collapse the various spellings onto the four levels the UI filters/styles use.
const normalizeLevel = (raw) => {
  switch (raw) {
    case 'FATAL':
    case 'SEVERE':
    case 'ERROR':   return 'ERROR'
    case 'WARNING':
    case 'WARN':    return 'WARN'
    case 'DEBUG':
    case 'TRACE':   return 'DEBUG'
    default:        return 'INFO'
  }
}

const activeFilter = ref('ALL')
const autoScroll = ref(true)
const terminalRef = ref(null)

// Render an ISO-Z capture timestamp as HH:MM:SS in the viewer's local timezone.
// getHours/Minutes/Seconds are local to the browser, so two people in different
// zones each see their own wall-clock time for the same line.
const formatLocalTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

const parseLine = (entry, defaultLevel = 'INFO') => {
  // Backend now ships { ts, text }; tolerate plain strings from an older
  // backend during a rolling update.
  const text = typeof entry === 'string' ? entry : (entry?.text ?? '')
  const ts = entry && typeof entry === 'object' ? entry.ts : null
  const m = text.match(LEVEL_PATTERN)
  // Derive the level from the line itself; fall back to the stream's default
  // (stderr lines without a recognizable level are treated as errors).
  const level = m ? normalizeLevel(m[1]) : defaultLevel
  // Prefer the authoritative capture time (shown in local tz); fall back to any
  // leading [HH:MM:SS] the server logged itself if no ts is present.
  let time = formatLocalTime(ts)
  if (!time) {
    const tsMatch = text.match(/\[(\d{2}:\d{2}:\d{2})\]/)
    time = tsMatch ? tsMatch[1] : ''
  }
  // Drop the server's own leading [HH:MM:SS] from the message — it's redundant
  // with the time column (which now shows local time) and would otherwise read
  // as a confusing double timestamp.
  const message = text.replace(/^\s*\[\d{2}:\d{2}:\d{2}\]\s*/, '')
  // Numeric sort key. Parse to a millisecond instant rather than comparing the
  // raw ISO strings lexicographically: iso_z_now() omits the ".ffffff" fraction
  // when microsecond == 0, so "…:00Z" would sort AFTER "…:00.5Z" as text
  // ('.' < 'Z') and reverse same-second lines. NaN when ts is absent/unparseable.
  const tsMs = ts ? Date.parse(ts) : NaN
  return { tsMs, time, level, message }
}

// Tag each line with a stream-scoped id so :key stays stable across filter
// toggles — index keys made Vue recycle DOM nodes carrying the previous
// line's level class, flashing the wrong color on filter swap.
const allLines = computed(() => {
  const stdout = (store.logs.stdout || []).map((entry, i) => ({ id: `stdout:${i}`, stream: 'stdout', ...parseLine(entry) }))
  const stderr = (store.logs.stderr || []).map((entry, i) => {
    const parsed = parseLine(entry, 'ERROR')
    return { id: `stderr:${i}`, stream: 'stderr', ...parsed }
  })
  // Interleave the two streams by capture timestamp so a crash's stderr shows
  // next to the stdout that produced it, instead of all stderr dumped after all
  // stdout. Only sort when EVERY line carries a parseable ts — a numeric key
  // gives a proper total order (transitive), and a STABLE sort keeps
  // same-instant lines in their per-stream arrival order. If any line lacks a
  // ts (older backend sending plain strings), skip sorting and fall back to the
  // previous stdout-then-stderr order rather than risk a non-transitive compare.
  const merged = [...stdout, ...stderr]
  if (merged.every((l) => Number.isFinite(l.tsMs))) {
    merged.sort((a, b) => a.tsMs - b.tsMs)
  }
  return merged
})

const filteredLines = computed(() => {
  if (activeFilter.value === 'ALL') return allLines.value
  return allLines.value.filter((l) => l.level === activeFilter.value)
})

watch(filteredLines, async () => {
  if (!autoScroll.value) return
  await nextTick()
  const el = terminalRef.value
  if (el) el.scrollTop = el.scrollHeight
}, { flush: 'post' })

const setFilter = (level) => { activeFilter.value = level }
const toggleAutoScroll = () => { autoScroll.value = !autoScroll.value }

const onSubmit = (event) => {
  event.preventDefault()
  store.sendConsoleCommand()
}

const cmdInputRef = ref(null)

// Park the caret after the recalled text. The value lands via the store on the
// next tick, and ArrowUp's suppressed default would otherwise have left the
// caret at position 0 — so a recalled command reads as ready to edit or resend.
const moveCaretToEnd = async () => {
  await nextTick()
  const el = cmdInputRef.value
  if (el) el.setSelectionRange(el.value.length, el.value.length)
}

const onHistoryPrev = () => {
  store.recallPreviousCommand()
  moveCaretToEnd()
}

const onHistoryNext = () => {
  store.recallNextCommand()
  moveCaretToEnd()
}
</script>

<template>
  <div class="console-page">
    <div class="console-page__bar">
      <div class="console-page__filters" role="group" aria-label="Log level filter">
        <button
          v-for="level in ['ALL','INFO','WARN','ERROR','DEBUG']"
          :key="level"
          type="button"
          class="console-page__filter"
          :class="[`console-page__filter--${level.toLowerCase()}`, { 'is-active': activeFilter === level }]"
          :aria-pressed="activeFilter === level"
          @click="setFilter(level)"
        >{{ level }}</button>
      </div>
      <div class="console-page__bar-actions">
        <button
          type="button"
          class="console-page__icon-btn"
          :class="{ 'is-active': autoScroll }"
          :aria-pressed="autoScroll"
          :title="autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'"
          @click="toggleAutoScroll"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
            <path d="M7 2v9M3 7l4 4 4-4" />
          </svg>
        </button>
        <AppButton variant="ghost" size="sm" :loading="store.logsLoading" @click="store.loadLogs">Refresh</AppButton>
      </div>
    </div>

    <div ref="terminalRef" class="console-page__terminal">
      <div v-if="!filteredLines.length" class="console-page__empty">
        <template v-if="store.logsLoading">Loading logs…</template>
        <template v-else-if="activeFilter === 'ALL'">No logs yet.</template>
        <template v-else>No {{ activeFilter }} entries.</template>
      </div>
      <div
        v-for="line in filteredLines"
        :key="line.id"
        class="console-page__line"
        :class="`console-page__line--${line.level.toLowerCase()}`"
      >
        <span v-if="line.time" class="console-page__line-time">{{ line.time }}</span>
        <span class="console-page__line-level">{{ line.level }}</span>
        <span class="console-page__line-msg">{{ line.message }}</span>
      </div>
    </div>

    <form class="console-page__cmd" @submit="onSubmit">
      <span class="console-page__cmd-prompt">›</span>
      <input
        ref="cmdInputRef"
        type="text"
        class="console-page__cmd-input"
        :value="store.consoleCommand"
        @input="store.setConsoleCommand($event.target.value)"
        @keydown.up.exact.prevent="onHistoryPrev"
        @keydown.down.exact.prevent="onHistoryNext"
        :disabled="!store.canSendCommand"
        :placeholder="store.canSendCommand ? 'Type a command and press Enter…' : 'Server not running'"
      />
      <AppButton
        type="submit"
        variant="primary"
        size="sm"
        :disabled="!store.canSendCommand || !store.consoleCommand.trim()"
        :loading="store.commandSending"
      >Send</AppButton>
    </form>
  </div>
</template>

<style scoped>
.console-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  /* No viewport math: ServerLayout's __content is `display: flex; flex-direction: column`
     (Step 2.1b), so flex: 1 fills remaining space cleanly. */
}

.console-page__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.console-page__filters {
  display: flex;
  gap: 2px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 2px;
}

.console-page__filter {
  background: transparent;
  border: none;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-disabled);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.console-page__filter:hover:not(.is-active) {
  color: var(--text-muted);
}

.console-page__filter.is-active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.console-page__filter--info.is-active   { color: var(--info); }
.console-page__filter--warn.is-active   { color: var(--warning); }
.console-page__filter--error.is-active  { color: var(--danger); }
.console-page__filter--debug.is-active  { color: var(--primary); }

.console-page__bar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.console-page__icon-btn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.console-page__icon-btn:hover {
  color: var(--text-secondary);
}

.console-page__icon-btn.is-active {
  background: rgba(249, 115, 22, 0.12);
  border-color: rgba(249, 115, 22, 0.35);
  color: var(--primary);
}

.console-page__icon-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.console-page__terminal {
  flex: 1;
  min-height: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  color: var(--text-muted);
}

.console-page__empty {
  color: var(--text-disabled);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--space-5) 0;
}

.console-page__line {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: 1px 0;
}

.console-page__line-time {
  color: var(--text-disabled);
  flex-shrink: 0;
  min-width: 56px;
}

.console-page__line-level {
  flex-shrink: 0;
  min-width: 40px;
  font-weight: 500;
}

.console-page__line--info .console-page__line-level   { color: #60a5fa; }
.console-page__line--warn .console-page__line-level   { color: var(--warning); }
.console-page__line--error .console-page__line-level  { color: var(--danger); }
.console-page__line--debug .console-page__line-level  { color: var(--primary); }

.console-page__line-msg {
  color: var(--text-secondary);
  word-break: break-word;
}

.console-page__cmd {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.console-page__cmd-prompt {
  font-family: var(--font-mono);
  color: var(--primary);
  flex-shrink: 0;
}

.console-page__cmd-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.console-page__cmd-input::placeholder {
  color: var(--text-disabled);
}

.console-page__cmd-input:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}
</style>
