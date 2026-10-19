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

// Java's Properties decoding of the hand-typed `\u00A7` / `\n` workaround that
// MOTDs used before the editor existed. The backend writes those two escapes
// through untouched and doubles every other backslash, so decoding exactly
// these, in one pass, previews what the game will show.
function decodeLegacy(raw) {
  return String(raw ?? '').replace(/\\(u[0-9a-fA-F]{4}|n)/g, (_, esc) =>
    esc === 'n' ? '\n' : String.fromCharCode(parseInt(esc.slice(1), 16))
  )
}

// What the editor works on: the old escapes turned into the characters they
// stand for (so toolbar positions line up with what is shown), and no `\r`,
// which a textarea drops and would throw selection offsets off.
export function normalizeMotd(raw) {
  return decodeLegacy(raw).replace(/\r/g, '')
}

// The MOTD's lines as `{ text, style }` segments. Style carries across the
// line break, as it does in-game.
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

// Advance widths (GUI px) of the vanilla font for ' '..'~', read from the 26.3
// client's font atlas the way the game measures glyphs (rightmost lit column
// + 1; space is a fixed 4). Bold adds 1 to every glyph, spaces included.
const ASCII_ADVANCES = '42466662444626266666666666225656766666666466666666666666666464663666665662653666666646666664247'
// ponytail: outside ASCII everything counts as 6, the width of nearly every
// accented Latin letter; read the full atlas if other scripts need centring.
const OTHER_ADVANCE = 6

// The width vanilla wraps the MOTD to: in 26.3 the 305px row, minus 4 padding,
// the 32px icon and 2. Clients up to 1.21 wrapped at 271.
export const MOTD_WIDTH = 267

export function glyphAdvance(ch, bold) {
  const code = ch.codePointAt(0)
  const base = code >= 32 && code <= 126 ? Number(ASCII_ADVANCES[code - 32]) : OTHER_ADVANCE
  return base + (bold ? 1 : 0)
}

function toSegments(chars) {
  const segments = []
  for (const { ch, style } of chars) {
    const last = segments[segments.length - 1]
    if (last?.style === style) last.text += ch
    else segments.push({ text: ch, style })
  }
  return segments
}

// One line word-wrapped the way vanilla's StringSplitter does it: break at the
// last space before the line overflows (that space is dropped), or mid-word
// when there is none.
function wrapLine(segments, width) {
  const chars = segments.flatMap((seg) => Array.from(seg.text, (ch) => ({ ch, style: seg.style })))
  const lines = []
  let start = 0
  do {
    let used = 0
    let lastSpace = -1
    let end = chars.length
    let next = chars.length
    for (let i = start; i < chars.length; i += 1) {
      if (chars[i].ch === ' ') lastSpace = i
      used += glyphAdvance(chars[i].ch, chars[i].style.bold)
      if (i > start && used > width) {
        ;[end, next] = lastSpace === -1 ? [i, i] : [lastSpace, lastSpace + 1]
        break
      }
    }
    lines.push(toSegments(chars.slice(start, end)))
    start = next
  } while (start < chars.length)
  return lines
}

// Every line the server list would lay out, wrapped. It shows the first two.
export function wrapMotd(raw, width = MOTD_WIDTH) {
  return parseMotd(raw).flatMap((line) => wrapLine(line, width))
}

// Leading spaces, wherever they sit among the line's opening § codes, are
// what centring replaces.
function stripLeadingSpaces(line) {
  let codes = ''
  let i = 0
  while (i < line.length) {
    if (line[i] === '§' && i + 1 < line.length) {
      codes += line.slice(i, i + 2)
      i += 2
    } else if (line[i] === ' ') {
      i += 1
    } else {
      break
    }
  }
  return codes + line.slice(i)
}

// Pads each line with spaces so it sits centred in the server list. Earlier
// padding is replaced, so centring twice changes nothing, and a line too wide
// to centre (it wraps) ends up flush left.
export function centerMotd(raw) {
  let carried = BASE
  return String(raw ?? '').split('\n').map((line) => {
    const text = Array.from(stripLeadingSpaces(line))
    let style = carried
    let width = 0
    let trailing = 0
    for (let i = 0; i < text.length; i += 1) {
      if (text[i] === '§') {
        if (i + 1 < text.length) style = applyCode(style, text[++i])
        continue
      }
      const advance = glyphAdvance(text[i], style.bold)
      width += advance
      trailing = text[i] === ' ' ? trailing + advance : 0
    }
    // The padding goes before the line's own codes, so it takes the style
    // carried in from the line above.
    const space = glyphAdvance(' ', carried.bold)
    carried = style
    const pad = Math.max(0, Math.round((MOTD_WIDTH - (width - trailing)) / 2 / space))
    return ' '.repeat(pad) + text.join('')
  }).join('\n')
}

export function colorHex(style) {
  return COLOR_HEX[style.color] ?? MOTD_DEFAULT_HEX
}

// Minecraft draws the drop shadow at a quarter of each channel.
export function shadowHex(hex) {
  const n = parseInt(hex.slice(1), 16)
  return `#${((n & 0xfcfcfc) >> 2).toString(16).padStart(6, '0')}`
}

// The style text typed at `index` of `raw` would get.
export function styleAt(raw, index) {
  const text = String(raw ?? '').slice(0, index)
  let style = BASE
  for (let i = 0; i < text.length - 1; i += 1) {
    if (text[i] === '§') style = applyCode(style, text[++i])
  }
  return style
}

// The § codes that recreate the style active at `index` of `raw`, so wrapping
// a selection can hand the text after it back its previous styling. Without
// `withColor`, just the formats: what a new colour code has to repeat, since
// a colour clears them in-game.
export function codesAt(raw, index, { withColor = true } = {}) {
  const style = styleAt(raw, index)
  const formats = Object.entries(MOTD_FORMATS).filter(([, flag]) => style[flag]).map(([code]) => `§${code}`)
  return (withColor && style.color ? `§${style.color}` : '') + formats.join('')
}

// An index sitting between a § and its code letter, moved back before the §,
// so nothing is ever inserted into the middle of a code.
export function snapIndex(raw, index) {
  for (let i = 0; i < index; i += 1) {
    if (raw[i] !== '§') continue
    if (i + 1 === index) return i
    i += 1
  }
  return index
}
