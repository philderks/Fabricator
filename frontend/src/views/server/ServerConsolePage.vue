<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
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
  // Synthetic restart marker separating the retained previous run from the
  // current one. It carries a real ts (so it still sorts into place) but no
  // level or message parsing — it renders as a divider, not a log line.
  if (entry && typeof entry === 'object' && entry.boundary) {
    return { tsMs: ts ? Date.parse(ts) : NaN, time: '', level: 'INFO', message: text, boundary: true }
  }
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

// Tag each line with an id so :key stays stable across filter toggles — index
// keys made Vue recycle DOM nodes carrying the previous line's level class,
// flashing the wrong color on filter swap.
//
// The id is derived from the line's *content*, not its position. loadLogs()
// returns a trailing window of the log, so once a server passes the limit every
// index shifts on each poll: with index keys Vue patched the shifted text into
// the existing nodes and never inserted anything, which meant a genuinely new
// line was indistinguishable from an old one — and so could not animate in.
// The `#n` suffix disambiguates lines that repeat verbatim within one poll.
const withIds = (entries, stream, defaultLevel) => {
  const seen = new Map()
  return entries.map((entry) => {
    const line = parseLine(entry, defaultLevel)
    const base = `${stream}|${line.tsMs}|${line.message}`
    const n = (seen.get(base) ?? 0) + 1
    seen.set(base, n)
    return { id: `${base}#${n}`, stream, ...line }
  })
}

const allLines = computed(() => {
  const stdout = withIds(store.logs.stdout || [], 'stdout', 'INFO')
  const stderr = withIds(store.logs.stderr || [], 'stderr', 'ERROR')
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

// --- Smooth reveal -----------------------------------------------------------
// Logs are polled on an interval, so without this a poll drops its whole batch
// of new lines into the terminal in a single frame — the console jumps in steps
// rather than streaming. We withhold newly-arrived lines and release them over a
// short window so output reads as continuous.

const REVEAL_BUDGET_MS = 900 // however big the backlog, it is fully out by then
const MIN_LINE_GAP_MS = 45   // ...but a couple of lines still land one at a time

// Someone who has asked the OS for less motion wants the text, not the effect.
const prefersReducedMotion = typeof window !== 'undefined'
  && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Counted from the END of allLines, so the count stays valid even when the log
// window slides and every absolute index shifts underneath us.
const hiddenCount = ref(0)

let rafId = 0
let lastFrame = 0
let deadline = 0
let carry = 0 // fractional lines owed from the previous frame

const stopDrip = () => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  carry = 0
}

const step = (now) => {
  // Clamp dt: a backgrounded tab stops firing frames, and without this the
  // catch-up frame on return would release the entire backlog at once.
  const dt = Math.min(now - lastFrame, 120)
  lastFrame = now
  const hidden = hiddenCount.value
  if (hidden <= 0) return stopDrip()
  // Pace against the time LEFT, not the budget as a whole. Dividing the
  // remaining lines by a fixed budget makes the rate fall as the backlog
  // drains, so the tail crawls and a large batch overruns the budget several
  // times over; against the remaining time the rate self-corrects and the
  // backlog lands on the deadline. The floor keeps a two-line trickle from
  // collapsing into a single pop.
  const timeLeft = Math.max(deadline - now, 16)
  carry += Math.max(1 / MIN_LINE_GAP_MS, hidden / timeLeft) * dt
  const release = Math.floor(carry)
  if (release > 0) {
    carry -= release
    hiddenCount.value = Math.max(0, hidden - release)
  }
  rafId = requestAnimationFrame(step)
}

const startDrip = () => {
  // A poll landing mid-drip refreshes the deadline, so its lines get the full
  // window too rather than being rushed out on the tail of the previous batch.
  deadline = performance.now() + REVEAL_BUDGET_MS
  if (rafId) return
  lastFrame = performance.now()
  carry = 1 // let the first new line through immediately; stagger the rest
  rafId = requestAnimationFrame(step)
}

// Identity of the last line we have already accounted for. Compared by content
// because ids carry a per-poll duplicate counter that can shift as the window
// slides.
const tailKey = (l) => `${l.stream}|${l.tsMs}|${l.message}`
let prevTailKey = null

watch(allLines, (lines) => {
  const nextTailKey = lines.length ? tailKey(lines[lines.length - 1]) : null
  const previous = prevTailKey
  prevTailKey = nextTailKey

  if (!lines.length) { hiddenCount.value = 0; stopDrip(); return }
  if (nextTailKey === previous) return // poll returned nothing new

  // First fill, or a wholesale replacement (server switch, manual refresh after
  // a clear): this is backfill, not live output. Dripping a thousand retained
  // lines would read as the page hanging, so show them at once.
  if (previous === null || prefersReducedMotion) { hiddenCount.value = 0; return }

  // Scan back for the previous tail; everything after it arrived since. Going
  // from the end also survives the window sliding, which moves the anchor's
  // index but not its position relative to the end.
  let anchor = -1
  for (let i = lines.length - 1; i >= 0; i--) {
    if (tailKey(lines[i]) === previous) { anchor = i; break }
  }
  // Anchor fell off the front of the window (or the log was replaced): there is
  // no meaningful "new" set to stagger, so reveal everything.
  if (anchor === -1) { hiddenCount.value = 0; return }

  // Both counts are tail-relative, so a poll landing mid-drip composes cleanly.
  hiddenCount.value += lines.length - 1 - anchor
  startDrip()
}, { immediate: true })

onUnmounted(stopDrip)

const filteredLines = computed(() => {
  const lines = allLines.value
  const hidden = Math.min(Math.max(hiddenCount.value, 0), lines.length)
  const released = hidden ? lines.slice(0, lines.length - hidden) : lines
  if (activeFilter.value === 'ALL') return released
  // Drop the restart divider under a level filter: it defaults to INFO, so it
  // would otherwise show up as the lone "entry" in an empty INFO view.
  return released.filter((l) => !l.boundary && l.level === activeFilter.value)
})

const scrollToBottom = () => {
  const el = terminalRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(filteredLines, async () => {
  if (!autoScroll.value) return
  await nextTick()
  scrollToBottom()
}, { flush: 'post' })

// Scrolling up to read something hands control away from auto-scroll; scrolling
// back to the bottom hands it back. Both fall out of one measurement, with no
// flag needed to tell a user scroll from the watcher's own: the programmatic
// scroll always lands at the bottom, so it re-affirms auto-scroll instead of
// cancelling it. Measuring in the handler (rather than trusting the event's
// arrival order) means a stale event still reads the current position.
const PIN_THRESHOLD_PX = 32 // ~two lines of slack, so "close enough" counts as pinned

const onTerminalScroll = () => {
  const el = terminalRef.value
  if (!el) return
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight <= PIN_THRESHOLD_PX
}

const setFilter = (level) => { activeFilter.value = level }

const toggleAutoScroll = async () => {
  autoScroll.value = !autoScroll.value
  if (!autoScroll.value) return
  // Catch up now. Waiting for the next line to arrive would leave the button
  // reading "on" while the view sits where it was.
  await nextTick()
  scrollToBottom()
}

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
          :title="autoScroll ? 'Auto-scroll on' : 'Auto-scroll off — click, or scroll to the bottom, to resume'"
          @click="toggleAutoScroll"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
            <path d="M7 2v9M3 7l4 4 4-4" />
          </svg>
        </button>
        <!-- Wrapped, not passed by reference: @click would hand loadLogs the
             MouseEvent as its `limit` argument. -->
        <AppButton variant="ghost" size="sm" :loading="store.logsLoading" @click="() => store.loadLogs()">Refresh</AppButton>
      </div>
    </div>

    <div ref="terminalRef" class="console-page__terminal" @scroll.passive="onTerminalScroll">
      <div v-if="!filteredLines.length" class="console-page__empty">
        <template v-if="store.logsLoading">Loading logs…</template>
        <template v-else-if="activeFilter === 'ALL'">No logs yet.</template>
        <template v-else>No {{ activeFilter }} entries.</template>
      </div>
      <template v-for="line in filteredLines" :key="line.id">
        <div v-if="line.boundary" class="console-page__boundary" role="separator">
          <span class="console-page__boundary-label">{{ line.message }}</span>
        </div>
        <div
          v-else
          class="console-page__line"
          :class="`console-page__line--${line.level.toLowerCase()}`"
        >
          <span v-if="line.time" class="console-page__line-time">{{ line.time }}</span>
          <span class="console-page__line-level">{{ line.level }}</span>
          <span class="console-page__line-msg">{{ line.message }}</span>
        </div>
      </template>
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

/* Runs once per node, on insert. Content-derived :keys mean Vue patches lines
   that were already on screen and only *inserts* genuinely new ones, so a poll
   animates its new arrivals and leaves the rest alone. transform is used rather
   than margin/height so an entering line never reflows the ones above it. */
@keyframes console-line-in {
  from { opacity: 0; transform: translateY(3px); }
  to   { opacity: 1; transform: none; }
}

.console-page__line,
.console-page__boundary {
  animation: console-line-in 170ms ease-out both;
}

@media (prefers-reduced-motion: reduce) {
  .console-page__line,
  .console-page__boundary {
    animation: none;
  }
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

/* Marks where the retained previous run ends and the current one begins. */
.console-page__boundary {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  color: var(--text-disabled);
  font-size: var(--text-xs);
}

.console-page__boundary::before,
.console-page__boundary::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-color);
}

.console-page__boundary-label {
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
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
/* Mobile: five level filters plus the two actions overflow a phone row. The
   filter group scrolls sideways rather than wrapping, which keeps it reading as
   one segmented control. */
@media (max-width: 768px) {
  .console-page__bar {
    gap: var(--space-2);
  }

  .console-page__filters {
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .console-page__filters::-webkit-scrollbar {
    display: none;
  }

  .console-page__filter {
    flex-shrink: 0;
  }

  .console-page__bar-actions {
    flex-shrink: 0;
  }
}
</style>
