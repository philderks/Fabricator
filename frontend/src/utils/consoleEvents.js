/**
 * Console event filters (#113): which game event a server log line reports.
 *
 * Read from the message right after the log prefix, as the backend's join
 * detection does (backend/server/manager.py): a player typing "Steve joined the
 * game" into chat logs it after "<Steve> ", so that line stays chat.
 *
 * Vanilla wording only. Chat plugins that reformat messages, a /say run by a
 * player ("[Steve] hi", indistinguishable from mods logging "[ModName] ...")
 * and death messages added by mods are not recognised.
 */

// "[12:00:00 INFO]" (Paper/Spigot), or "[time] [thread/INFO]" plus the optional
// Forge/NeoForge "[category]". Same alternatives as the backend's _LOG_PREFIX.
const LOG_PREFIX = /^(?:\[[^\]]*INFO\]|\[[^\]]+\] \[[^\]]*INFO\](?: \[[^\]]*\])?): /
// 26.3 logs server messages as "System chat: ...". Any "<word> chat: " marker is
// skipped, so player chat is covered too if it gets one.
const CHAT_MARKER = /^[a-z]+ chat: /i
// eslint-disable-next-line no-control-regex
const ANSI = /\x1b\[[0-9;]*m/g

// A player name as the backend reads it: none of the chat brackets or ":",
// spaces allowed (Geyser gamertags).
const NAME = String.raw`[^<>\[\]:]+?`

// What follows the name in vanilla death messages, 1.7 to today (en_us
// "death.*" keys). Longer wordings ("was slain by X using Y", "fell off a
// ladder", "... whilst fighting X") start with one of these.
const DEATH_PHRASES = [
  'was (?:slain|shot|killed|blown|squashed|squished|pricked|roasted|fireballed|pummeled|impaled|struck by lightning|stung|poked|obliterated|skewered|frozen|burned|smashed|spit|doomed|knocked)',
  'drowned',
  'died',
  'blew up',
  'burned to death',
  'hit the ground too hard',
  'fell',
  'went up in flames',
  'went off with a bang',
  'walked into',
  'tried to swim in lava',
  'suffocated in a wall',
  'starved to death',
  'withered away',
  'froze to death',
  'experienced kinetic energy',
  'discovered the floor was lava',
  'left the confines of this world',
  "didn't want to live",
  'got finished off'
]

// First match wins, so chat comes before anything a player could type.
const EVENTS = [
  // <Steve> hi · * Steve waves (/me) · [Server] hi (/say from the console,
  // [Rcon] over RCON, [@] from a command block); 1.19.1+ may add [Not Secure].
  ['CHAT', /^(?:\[Not Secure\] )?(?:<[^<>]+> |\* \S+ |\[(?:Server|Rcon|@)\] )/],
  ['JOIN', new RegExp(`^${NAME} (?:joined|left) the game`)],
  // Achievements before 1.12, advancements after.
  ['ADVANCEMENT', new RegExp(`^${NAME} has (?:made the advancement|completed the challenge|reached the goal|just earned the achievement) \\[`)],
  ['DEATH', new RegExp(`^${NAME} (?:${DEATH_PHRASES.join('|')})(?: |$)`)]
]

export const CONSOLE_EVENTS = EVENTS.map(([event]) => event)

/** 'CHAT' | 'JOIN' | 'ADVANCEMENT' | 'DEATH' for a raw log line, else null. */
export function consoleEvent(text) {
  const clean = text.replace(ANSI, '')
  const prefix = clean.match(LOG_PREFIX)
  if (!prefix) return null
  const body = clean.slice(prefix[0].length).replace(CHAT_MARKER, '')
  return EVENTS.find(([, pattern]) => pattern.test(body))?.[0] ?? null
}
