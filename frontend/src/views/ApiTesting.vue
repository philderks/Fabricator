<script setup>
import { ref, onMounted } from 'vue'
import * as modrinthApi from '../api/modrinth'
import * as serversApi from '../api/servers'

// Server Status
const serverStatus = ref(null)
const serverLoading = ref(false)

// Search
const searchQuery = ref('')
const searchMcVersion = ref('1.21.3')
const searchLoader = ref('fabric')
const searchResults = ref(null)
const searchLoading = ref(false)

// Mod Details
const modId = ref('')
const modDetails = ref(null)
const modVersions = ref(null)
const modLoading = ref(false)

// Install Mod
const installModId = ref('')
const installMcVersion = ref('1.21.3')
const installLoader = ref('fabric')
const installResult = ref(null)
const installLoading = ref(false)

// Categories & Loaders
const categories = ref(null)
const loaders = ref(null)
const gameVersions = ref(null)

// Get Server Status
const getStatus = async () => {
  serverLoading.value = true
  try {
    serverStatus.value = await serversApi.getServerStatus()
  } catch (e) {
    serverStatus.value = { error: e.message }
  }
  serverLoading.value = false
}

// Start Server
const startServer = async () => {
  serverLoading.value = true
  try {
    serverStatus.value = await serversApi.startServer(1) // Mock server ID
  } catch (e) {
    serverStatus.value = { error: e.message }
  }
  serverLoading.value = false
}

// Stop Server
const stopServer = async () => {
  serverLoading.value = true
  try {
    serverStatus.value = await serversApi.stopServer(1) // Mock server ID
  } catch (e) {
    serverStatus.value = { error: e.message }
  }
  serverLoading.value = false
}

// Search Mods
const searchMods = async () => {
  searchLoading.value = true
  try {
    searchResults.value = await modrinthApi.searchMods({
      query: searchQuery.value,
      version: searchMcVersion.value,
      loader: searchLoader.value,
      limit: 10
    })
  } catch (e) {
    searchResults.value = { error: e.message }
  }
  searchLoading.value = false
}

// Get Mod Details
const getMod = async () => {
  if (!modId.value) return
  modLoading.value = true
  try {
    modDetails.value = await modrinthApi.getModDetails(modId.value)
  } catch (e) {
    modDetails.value = { error: e.message }
  }
  modLoading.value = false
}

// Get Mod Versions
const getModVersions = async () => {
  if (!modId.value) return
  modLoading.value = true
  try {
    modVersions.value = await modrinthApi.getModVersions(modId.value)
  } catch (e) {
    modVersions.value = { error: e.message }
  }
  modLoading.value = false
}

// Install Mod
const installMod = async () => {
  if (!installModId.value) return
  installLoading.value = true
  try {
    installResult.value = await modrinthApi.installMod(installModId.value, {
      mc_version: installMcVersion.value,
      loader: installLoader.value
    })
  } catch (e) {
    installResult.value = { error: e.message }
  }
  installLoading.value = false
}

// Load Categories, Loaders, Game Versions
const loadMetadata = async () => {
  try {
    const [cat, load, ver] = await Promise.all([
      modrinthApi.getCategories(),
      modrinthApi.getLoaders(),
      modrinthApi.getGameVersions()
    ])
    categories.value = cat
    loaders.value = load
    gameVersions.value = ver
  } catch (e) {
    console.error('Failed to load metadata:', e)
  }
}

onMounted(() => {
  getStatus()
  loadMetadata()
})
</script>

<template>
  <div id="testing">
    <header>
      <h1>🎮 Fabricator API Tester</h1>
    </header>
    
    <main>
      <!-- Server Management -->
      <section class="card">
        <h2>🖥️ Server Management</h2>
        <div class="button-group">
          <button @click="getStatus" :disabled="serverLoading">Get Status</button>
          <button @click="startServer" :disabled="serverLoading">Start Server</button>
          <button @click="stopServer" :disabled="serverLoading">Stop Server</button>
        </div>
        <pre v-if="serverStatus" class="result">{{ JSON.stringify(serverStatus, null, 2) }}</pre>
      </section>

      <!-- Search Mods -->
      <section class="card">
        <h2>🔍 Search Mods</h2>
        <div class="form-group">
          <input v-model="searchQuery" placeholder="Search query (e.g., 'sodium')" />
          <input v-model="searchMcVersion" placeholder="MC Version (e.g., 1.21.3)" />
          <input v-model="searchLoader" placeholder="Loader (fabric/forge)" />
          <button @click="searchMods" :disabled="searchLoading">Search</button>
        </div>
        <pre v-if="searchResults" class="result">{{ JSON.stringify(searchResults, null, 2) }}</pre>
      </section>

      <!-- Mod Details -->
      <section class="card">
        <h2>📦 Mod Details & Versions</h2>
        <div class="form-group">
          <input v-model="modId" placeholder="Mod ID (e.g., AANobbMI)" />
          <button @click="getMod" :disabled="modLoading">Get Mod</button>
          <button @click="getModVersions" :disabled="modLoading">Get Versions</button>
        </div>
        <div v-if="modDetails">
          <h3>Mod Details:</h3>
          <pre class="result">{{ JSON.stringify(modDetails, null, 2) }}</pre>
        </div>
        <div v-if="modVersions">
          <h3>Mod Versions:</h3>
          <pre class="result">{{ JSON.stringify(modVersions, null, 2) }}</pre>
        </div>
      </section>

      <!-- Install Mod -->
      <section class="card">
        <h2>⬇️ Install Mod</h2>
        <div class="form-group">
          <input v-model="installModId" placeholder="Mod ID (e.g., AANobbMI)" />
          <input v-model="installMcVersion" placeholder="MC Version (e.g., 1.21.3)" />
          <input v-model="installLoader" placeholder="Loader (fabric/forge)" />
          <button @click="installMod" :disabled="installLoading">Install Mod</button>
        </div>
        <pre v-if="installResult" class="result">{{ JSON.stringify(installResult, null, 2) }}</pre>
      </section>

      <!-- Metadata -->
      <section class="card">
        <h2>📋 Metadata</h2>
        <div class="metadata-grid">
          <div v-if="categories">
            <h3>Categories ({{ categories.length }})</h3>
            <div class="tags">
              <span v-for="cat in categories.slice(0, 10)" :key="cat" class="tag">{{ cat }}</span>
            </div>
          </div>
          <div v-if="loaders">
            <h3>Loaders ({{ loaders.length }})</h3>
            <div class="tags">
              <span v-for="loader in loaders" :key="loader" class="tag">{{ loader }}</span>
            </div>
          </div>
          <div v-if="gameVersions">
            <h3>Game Versions ({{ gameVersions.length }})</h3>
            <div class="tags">
              <span v-for="ver in gameVersions.slice(0, 10)" :key="ver" class="tag">{{ ver }}</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
* {
  box-sizing: border-box;
}

header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 2rem;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

h1 {
  margin: 0;
  font-size: 2rem;
}

main {
  max-width: 1200px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

h2 {
  margin-top: 0;
  color: #333;
  border-bottom: 2px solid #667eea;
  padding-bottom: 0.5rem;
}

h3 {
  color: #555;
  margin-top: 1.5rem;
}

.button-group {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

button {
  background: #667eea;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  transition: background 0.2s;
}

button:hover:not(:disabled) {
  background: #5568d3;
}

button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.form-group {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

input {
  flex: 1;
  min-width: 200px;
  padding: 0.75rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 1rem;
}

input:focus {
  outline: none;
  border-color: #667eea;
}

.result {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 1rem;
  overflow-x: auto;
  font-size: 0.875rem;
  max-height: 400px;
  overflow-y: auto;
}

.metadata-grid {
  display: grid;
  gap: 1.5rem;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.tag {
  background: #e9ecef;
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.875rem;
  color: #495057;
}
</style>
