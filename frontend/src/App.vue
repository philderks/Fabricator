<script setup>
import ToastContainer from './components/common/ToastContainer.vue'
</script>

<template>
  <router-view />
  <ToastContainer />
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #0f1419;
  color: #e4e6eb;
  overflow-x: hidden;
}

#app {
  min-height: 100vh;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #1a1f29;
}

::-webkit-scrollbar-thumb {
  background: #2a3441;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #3a4551;
}
</style>
