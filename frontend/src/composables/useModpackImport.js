import { ref } from 'vue'
import { getProjectDetails, searchModpacks } from '../api/modrinth'
import { isLoaderCategory } from '../utils/loaderKind'

/**
 * Extract a Modrinth project slug or ID from a URL, slug, or raw ID.
 */
export function parseProjectRef(input) {
  const raw = (input || '').trim()
  if (!raw) {
    return ''
  }

  if (!raw.startsWith('http://') && !raw.startsWith('https://')) {
    return raw.replace(/^@/, '')
  }

  try {
    const parsed = new URL(raw)
    const parts = parsed.pathname.split('/').filter(Boolean)
    if ((parts[0] === 'modpack' || parts[0] === 'project') && parts[1]) {
      return parts[1]
    }
    return parts[parts.length - 1] || ''
  } catch {
    return ''
  }
}

/**
 * Normalize a Modrinth project/search-hit into a consistent shape.
 */
export function normalizeModpack(project) {
  return {
    id: project.project_id || project.id,
    slug: project.slug || '',
    title: project.title || project.name || project.slug || 'Unknown Modpack',
    description: project.description || '',
    downloads: project.downloads || 0,
    iconUrl: project.icon_url || '',
    projectType: project.project_type || 'modpack',
    // What the pack actually supports. Kept because a selected pack is checked
    // against the form's version and loader — dropping these left the search
    // path with no way to know it was heading for an incompatible install
    // until the create request came back and failed.
    //
    // The two sources spell this differently and `versions` is a trap: on a
    // /project response it is a list of version IDs (hex), while on a /search
    // hit it is the game-version list. Read the project's explicit fields
    // first, so a link-resolved pack is never compared against hex IDs and
    // warned about every time.
    gameVersions: Array.isArray(project.game_versions)
      ? project.game_versions
      : (Array.isArray(project.versions) ? project.versions : []),
    loaders: (
      Array.isArray(project.loaders)
        ? project.loaders
        : (Array.isArray(project.categories) ? project.categories : []).filter(isLoaderCategory)
    ).map((value) => String(value).toLowerCase())
  }
}

function isNotFoundError(error) {
  if (!error) {
    return false
  }
  if (error.status === 404) {
    return true
  }
  return String(error.message || '').toLowerCase().includes('not found')
}

/**
 * Composable that encapsulates modpack search and link-resolution logic.
 *
 * @param {Object} options
 * @param {import('vue').Ref<string>|() => string} options.mcVersion
 * @param {import('vue').Ref<string>|() => string} options.loader
 */
export function useModpackImport({ mcVersion, loader } = {}) {
  const searchQuery = ref('')
  const modpackLink = ref('')
  const searchResults = ref([])
  const selectedModpack = ref(null)
  const loading = ref(false)
  const resolving = ref(false)
  const searchDone = ref(false)
  const errorMessage = ref('')
  // True while the results on screen are the popular list rather than an answer
  // to something typed — the two need different headings and empty-state copy.
  const showingPopular = ref(false)

  const getVersion = () => (typeof mcVersion === 'function' ? mcVersion() : mcVersion?.value) || ''
  const getLoader = () => (typeof loader === 'function' ? loader() : loader?.value) || ''

  function selectPack(pack) {
    selectedModpack.value = normalizeModpack(pack)
    errorMessage.value = ''
  }

  function clearSelection() {
    selectedModpack.value = null
  }

  function resetAll() {
    searchQuery.value = ''
    modpackLink.value = ''
    searchResults.value = []
    selectedModpack.value = null
    loading.value = false
    resolving.value = false
    searchDone.value = false
    errorMessage.value = ''
    showingPopular.value = false
  }

  /**
   * Populate the results with the most-downloaded packs.
   *
   * Not a separate endpoint: the backend already sorts by downloads
   * (index='downloads'), so an empty query IS the popular list. Callers pass
   * the version/loader constraint implicitly — the browser modal is bound to a
   * real server and must stay filtered to what it can actually install, while
   * the create modal has nothing chosen yet and gets everything.
   */
  function loadPopular() {
    return performSearch('', { allowEmpty: true })
  }

  async function performSearch(queryOverride, { allowEmpty = false } = {}) {
    const query = (queryOverride ?? searchQuery.value ?? '').trim()
    // An empty query is only meaningful when it was asked for. Otherwise it
    // means the box was cleared, and showing the popular list there would look
    // like search results for nothing.
    if (!query && !allowEmpty) {
      searchResults.value = []
      searchDone.value = false
      showingPopular.value = false
      return
    }
    showingPopular.value = !query

    loading.value = true
    searchDone.value = false
    errorMessage.value = ''
    try {
      const response = await searchModpacks({
        query,
        version: getVersion(),
        loader: getLoader(),
        limit: 12
      })
      searchResults.value = Array.isArray(response.hits) ? response.hits : []
    } catch (error) {
      searchResults.value = []
      errorMessage.value = error.message || 'Failed to search modpacks.'
    } finally {
      loading.value = false
      searchDone.value = true
    }
  }

  async function resolveByLink() {
    const projectRef = parseProjectRef(modpackLink.value)
    if (!projectRef) {
      errorMessage.value = 'Enter a valid Modrinth modpack link, slug, or project ID.'
      return
    }

    resolving.value = true
    errorMessage.value = ''
    try {
      const project = await getProjectDetails(projectRef)
      if (project.project_type !== 'modpack') {
        errorMessage.value = 'This project exists but is not a modpack.'
        return
      }
      searchResults.value = [project]
      selectPack(project)
    } catch (error) {
      if (isNotFoundError(error)) {
        errorMessage.value = `No exact modpack found for "${projectRef}". Showing search results instead.`
        searchQuery.value = projectRef
        await performSearch(projectRef)
      } else {
        errorMessage.value = error.message || 'Could not resolve modpack from link.'
      }
    } finally {
      resolving.value = false
    }
  }

  return {
    searchQuery,
    modpackLink,
    searchResults,
    selectedModpack,
    loading,
    resolving,
    searchDone,
    showingPopular,
    errorMessage,
    selectPack,
    clearSelection,
    resetAll,
    performSearch,
    loadPopular,
    resolveByLink
  }
}
