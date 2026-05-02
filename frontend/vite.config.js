import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
// Note: package.json overrides rollup to 4.18.0 to avoid patch-package dependency issues
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true, // Listen on all addresses for dev container
    port: 3000,
    watch: {
      // WSL2's inotify misses many file change events; polling is more reliable
      // in the dev container even though it costs a bit of CPU.
      usePolling: true,
      interval: 300
    },
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
