import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@fontsource-variable/dm-sans'
import './style.css'
import './assets/global.css'
import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/client'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// On any 401 from the API (session expired), drop auth state and route to login.
const auth = useAuthStore()
setUnauthorizedHandler(() => {
  auth.markUnauthenticated()
  if (router.currentRoute.value.name !== 'Login') {
    router.push({ name: 'Login' })
  }
})

app.mount('#app')
