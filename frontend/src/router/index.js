import { createRouter, createWebHistory } from 'vue-router'
import Servers from '../views/Servers.vue'
import ServerDashboard from '../views/ServerDashboard.vue'
import DesignSystem from '../views/DesignSystem.vue'

const routes = [
  {
    path: '/',
    name: 'Servers',
    component: Servers
  },
  {
    path: '/server/:id',
    name: 'ServerDashboard',
    component: ServerDashboard
  },
  {
    path: '/design-system',
    name: 'DesignSystem',
    component: DesignSystem
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
