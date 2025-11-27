import { createRouter, createWebHistory } from 'vue-router'
import Servers from '../views/Servers.vue'
import ServerDashboard from '../views/ServerDashboard.vue'
import ApiTesting from '../views/ApiTesting.vue'

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
    path: '/api-testing',
    name: 'ApiTesting',
    component: ApiTesting
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
