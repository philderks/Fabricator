/**
 * Compact number formatter — produces "1.2M" / "3.4K" style for large counts.
 * Used by mod/modpack download displays. Returns "0" for falsy input.
 */
export function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M'
  if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K'
  return num.toString()
}

/**
 * Length-bounded text truncation with ellipsis. Defaults to 100 chars.
 * Returns '' for falsy input.
 */
export function truncate(text, length = 100) {
  if (!text) return ''
  return text.length > length ? `${text.slice(0, length)}...` : text
}

export function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) {
    return '—'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[idx]}`
}
