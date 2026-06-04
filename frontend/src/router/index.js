import { createRouter, createWebHistory } from 'vue-router'
import RootLayout from '../layouts/RootLayout.vue'
import Servers from '../views/Servers.vue'
import ServerLayout from '../layouts/ServerLayout.vue'
import ServerOverviewPage from '../views/server/ServerOverviewPage.vue'
import ServerConsolePage from '../views/server/ServerConsolePage.vue'
import ServerPlayersPage from '../views/server/ServerPlayersPage.vue'
import ServerModsPage from '../views/server/ServerModsPage.vue'
import ServerFilesPage from '../views/server/ServerFilesPage.vue'
import ServerBackupsPage from '../views/server/ServerBackupsPage.vue'
import ServerPlayitPage from '../views/server/ServerPlayitPage.vue'
import ServerSettingsPage from '../views/server/ServerSettingsPage.vue'

const routes = [
  {
    path: '/',
    component: RootLayout,
    children: [
      { path: '', name: 'Servers', component: Servers }
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
      { path: 'settings', name: 'ServerSettings', component: ServerSettingsPage }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
