// Minecraft legacy § formatting, as the multiplayer server list draws a MOTD.

// The 16 vanilla colour codes. `name` keys the i18n label.
export const MOTD_COLORS = [
  { code: '0', name: 'black', hex: '#000000' },
  { code: '1', name: 'darkBlue', hex: '#0000AA' },
  { code: '2', name: 'darkGreen', hex: '#00AA00' },
  { code: '3', name: 'darkAqua', hex: '#00AAAA' },
  { code: '4', name: 'darkRed', hex: '#AA0000' },
  { code: '5', name: 'darkPurple', hex: '#AA00AA' },
  { code: '6', name: 'gold', hex: '#FFAA00' },
  { code: '7', name: 'gray', hex: '#AAAAAA' },
  { code: '8', name: 'darkGray', hex: '#555555' },
  { code: '9', name: 'blue', hex: '#5555FF' },
  { code: 'a', name: 'green', hex: '#55FF55' },
  { code: 'b', name: 'aqua', hex: '#55FFFF' },
  { code: 'c', name: 'red', hex: '#FF5555' },
  { code: 'd', name: 'lightPurple', hex: '#FF55FF' },
  { code: 'e', name: 'yellow', hex: '#FFFF55' },
  { code: 'f', name: 'white', hex: '#FFFFFF' }
]

// Format code → style flag. Reset ('r') is handled separately.
export const MOTD_FORMATS = { l: 'bold', o: 'italic', n: 'underline', m: 'strikethrough', k: 'obfuscated' }

// The server list draws MOTD text gray until a code says otherwise; §r returns to it.
export const MOTD_DEFAULT_HEX = '#808080'

const COLOR_HEX = Object.fromEntries(MOTD_COLORS.map((c) => [c.code, c.hex]))
const BASE = Object.freeze({ color: null })

// Vanilla rules: a colour code also clears every format, §r clears everything,
// and an unknown code is swallowed without effect.
function applyCode(style, code) {
  const c = code.toLowerCase()
  if (COLOR_HEX[c]) return { color: c }
  if (c === 'r') return BASE
  return MOTD_FORMATS[c] ? { ...style, [MOTD_FORMATS[c]]: true } : style
}

// Java's Properties decoding of the hand-typed `§` / `\n` workaround that
// MOTDs used before the editor existed, so those still preview correctly.
function decodeLegacy(raw) {
  return String(raw ?? '')
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
    .replace(/\\n/g, '\n')
}

// Up to two lines (all the server list shows) of `{ text, style }` segments.
// Style carries across the line break, as it does in-game.
export function parseMotd(raw) {
  const text = decodeLegacy(raw)
  const lines = [[]]
  let style = BASE
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (ch === '§') {
      if (i + 1 < text.length) style = applyCode(style, text[++i])
      continue
    }
    if (ch === '\n') {
      if (lines.length === 2) break
      lines.push([])
      continue
    }
    const line = lines[lines.length - 1]
    const last = line[line.length - 1]
    if (last?.style === style) last.text += ch
    else line.push({ text: ch, style })
  }
  return lines
}

export function colorHex(style) {
  return COLOR_HEX[style.color] ?? MOTD_DEFAULT_HEX
}

// Minecraft draws the drop shadow at a quarter of each channel.
export function shadowHex(hex) {
  const n = parseInt(hex.slice(1), 16)
  return `#${((n & 0xfcfcfc) >> 2).toString(16).padStart(6, '0')}`
}

// The § codes that recreate the style active at `index` of `raw`, so wrapping
// a selection can hand the text after it back its previous styling.
export function codesAt(raw, index) {
  const text = String(raw ?? '').slice(0, index)
  let style = BASE
  for (let i = 0; i < text.length - 1; i += 1) {
    if (text[i] === '§') style = applyCode(style, text[++i])
  }
  const formats = Object.entries(MOTD_FORMATS).filter(([, flag]) => style[flag]).map(([code]) => `§${code}`)
  return (style.color ? `§${style.color}` : '') + formats.join('')
}
