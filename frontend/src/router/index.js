import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginPage from '../views/LoginPage.vue'
import SetupPage from '../views/SetupPage.vue'
import RootLayout from '../layouts/RootLayout.vue'
import Servers from '../views/Servers.vue'
import IntegrationsPage from '../views/IntegrationsPage.vue'
import ServerLayout from '../layouts/ServerLayout.vue'
import ServerOverviewPage from '../views/server/ServerOverviewPage.vue'
import ServerConsolePage from '../views/server/ServerConsolePage.vue'
import ServerPlayersPage from '../views/server/ServerPlayersPage.vue'
import ServerModsPage from '../views/server/ServerModsPage.vue'
import ServerFilesPage from '../views/server/ServerFilesPage.vue'
import ServerBackupsPage from '../views/server/ServerBackupsPage.vue'
import ServerPlayitPage from '../views/server/ServerPlayitPage.vue'
import ServerSettingsPage from '../views/server/ServerSettingsPage.vue'
import ServerGeneralSettingsPage from '../views/server/ServerGeneralSettingsPage.vue'

const routes = [
  { path: '/login', name: 'Login', component: LoginPage },
  { path: '/setup', name: 'Setup', component: SetupPage },
  {
    path: '/',
    component: RootLayout,
    children: [
      { path: '', name: 'Servers', component: Servers },
      { path: 'integrations', name: 'Integrations', component: IntegrationsPage }
    ]
  },
  {
    path: '/server/:id',
    component: ServerLayout,
    children: [
      { path: '', redirect: { name: 'ServerOverview' } },
      { path: 'overview', name: 'ServerOverview', component: ServerOverviewPage },
      { path: 'console',  name: 'ServerConsole',  component: ServerConsolePage },
      { path: 'players',  name: 'ServerPlayers',  component: ServerPlayersPage },
      { path: 'mods',     name: 'ServerMods',     component: ServerModsPage },
      { path: 'files',    name: 'ServerFiles',    component: ServerFilesPage },
      { path: 'backups',  name: 'ServerBackups',  component: ServerBackupsPage },
      { path: 'playit',   name: 'ServerPlayit',   component: ServerPlayitPage },
      { path: 'properties', name: 'ServerSettings', component: ServerSettingsPage },
      { path: 'settings', name: 'ServerGeneralSettings', component: ServerGeneralSettingsPage }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) {
    try {
      await auth.checkStatus()
    } catch (_) {
      // Status call failed (server/network): treat as unauthenticated and leave
      // `checked` false so the next navigation retries. `enabled` stays true and
      // `needsSetup` false (safe defaults), so the next branches route to /login.
    }
  }
  if (!auth.enabled) return true // auth turned off on the backend

  // First-boot: no credential yet -> force the setup page, lock everything else.
  if (auth.needsSetup) {
    return to.name === 'Setup' ? true : { name: 'Setup' }
  }
  // Configured: keep users off the setup page.
  if (to.name === 'Setup') {
    return auth.isAuthenticated ? { name: 'Servers' } : { name: 'Login' }
  }
  if (to.name === 'Login') {
    return auth.isAuthenticated ? { name: 'Servers' } : true
  }
  if (auth.isAuthenticated) return true
  return { name: 'Login', query: { redirect: to.fullPath } }
})

export default router
