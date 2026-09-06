/** Settings sub-pages.
 *
 * Settings is an index of these plus About, which stays on the index itself
 * because it is two read-only rows — a sub-page holding nothing you can act on
 * is a click that buys nothing.
 *
 * Shared by the page (which renders the index and the active section) and
 * AppTopbar (which needs the label for the breadcrumb), so the two can't drift.
 * `key` is the :section route param.
 */
export const SETTINGS_SECTIONS = [
  {
    key: 'autostart',
    label: 'Auto-start',
    description: 'What happens to this server when Fabricator starts up.',
    // Per-server: there is nothing to auto-start on the server-less route.
    serverOnly: true,
    hiddenWhenManaged: true
  },
  {
    key: 'display',
    label: 'Display',
    description: 'Units and readouts used across the interface.'
  },
  {
    key: 'java',
    label: 'Java',
    description: 'Installed runtimes, and installing new ones.',
    hiddenWhenManaged: true
  },
  {
    key: 'mcp',
    label: 'MCP',
    description: 'Model Context Protocol access for AI assistants.',
    hiddenWhenManaged: true
  },
  {
    key: 'security',
    label: 'Security',
    description: 'The password used to unlock Fabricator, and whether one is required.',
    // Deliberately NOT gated on auth being enabled: this section is the only
    // way back once the password is turned off, so hiding it in that state
    // would make disabling a one-way door.
    hiddenWhenManaged: true
  }
]

/** Sections available in a given context, in index order. */
export function availableSettingsSections({ hasServer = false, managed = false, authEnabled = false } = {}) {
  return SETTINGS_SECTIONS.filter((section) => {
    if (section.serverOnly && !hasServer) return false
    if (section.hiddenWhenManaged && managed) return false
    if (section.requiresAuth && !authEnabled) return false
    return true
  })
}

/** Display name for a section key; '' when the key is unknown. */
export function settingsSectionLabel(key) {
  return SETTINGS_SECTIONS.find((section) => section.key === key)?.label || ''
}
