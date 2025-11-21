<script setup>
import { ref } from 'vue'
import ServerStatus from './components/ServerStatus.vue'

const appTitle = ref('Minecraft Server Manager')
</script>

<template>
  <div id="app">
    <header>
      <h1>{{ appTitle }}</h1>
    </header>
    <main>
      <ServerStatus />
    </main>
  </div>
</template>

<style scoped>
header {
  background: #2c3e50;
  color: white;
  padding: 1.5rem;
  text-align: center;
}

main {
  max-width: 800px;
  margin: 2rem auto;
  padding: 0 1rem;
}

h1 {
  margin: 0;
}
</style>
