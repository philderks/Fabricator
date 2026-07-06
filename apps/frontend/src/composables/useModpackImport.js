import { ref } from 'vue'
import { getProjectDetails, searchModpacks } from '../api/modrinth'

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
    projectType: project.project_type || 'modpack'
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
  }

  async function performSearch(queryOverride) {
    const query = (queryOverride || searchQuery.value || '').trim()
    if (!query) {
      searchResults.value = []
      searchDone.value = false
      return
    }

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
    errorMessage,
    selectPack,
    clearSelection,
    resetAll,
    performSearch,
    resolveByLink
  }
}
