/** Modrinth project page links for installed content.
 *
 * Two identity sources feed in, in order of trust:
 *   - `mod.modrinth` — the install manifest the backend wrote at install time.
 *     Authoritative: the jar provably came from that project.
 *   - `mod.modrinthGuess` — resolved client-side from the jar filename by the
 *     enricher. Only set when the filename verifiably matches the project, but
 *     still an inference, so it never overrides the manifest.
 *
 * Hand-dropped jars that match no project have neither and get no link.
 *
 * A bare project ref (`{ projectId, slug }`) is also accepted, which is what
 * the installed-modpack record looks like.
 */

const PROJECT_BASE = 'https://modrinth.com/project'

/**
 * Build the Modrinth page URL for an installed mod entry.
 *
 * Uses the `/project/<ref>` form rather than `/mod/<ref>` or `/plugin/<ref>`:
 * Modrinth redirects it to the right project type, so one shape covers mods,
 * plugins, and modpacks without the caller knowing which it is.
 *
 * @param {{ modrinth?: object | null, modrinthGuess?: object | null } | null} mod
 * @returns {string | null} URL, or null when the entry has no known project
 */
export function modrinthProjectUrl(mod) {
  const ref = mod?.modrinth || mod?.modrinthGuess || mod
  // Prefer the slug: it's the human-readable URL Modrinth itself shows, and
  // the id works only as a fallback for manifests written before a project
  // lookup succeeded.
  const key = ref?.slug || ref?.projectId || ref?.id
  if (!key || typeof key !== 'string') return null
  return `${PROJECT_BASE}/${encodeURIComponent(key)}`
}
