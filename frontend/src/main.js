import { createApp } from 'vue'
import '@fontsource-variable/dm-sans'
import './style.css'
import './assets/global.css'
import App from './App.vue'
import router from './router'

createApp(App).use(router).mount('#app')
