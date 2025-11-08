<script setup>
import { ref, onMounted } from 'vue'

const status = ref(null)
const loading = ref(true)
const error = ref(null)

const fetchStatus = async () => {
  loading.value = true
  error.value = null
  
  try {
    const response = await fetch('/api/status')
    if (!response.ok) {
      throw new Error('Failed to fetch server status')
    }
    const data = await response.json()
    status.value = data
  } catch (err) {
    error.value = err.message
    console.error('Error fetching status:', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStatus()
})
</script>

<template>
  <div class="server-status">
    <h2>Server Status</h2>
    
    <div v-if="loading" class="loading">
      Loading server status...
    </div>
    
    <div v-else-if="error" class="error">
      <p>Error: {{ error }}</p>
      <button @click="fetchStatus">Retry</button>
    </div>
    
    <div v-else-if="status" class="status-info">
      <div class="status-card">
        <div class="status-item">
          <strong>Status:</strong>
          <span :class="['badge', status.status]">{{ status.status }}</span>
        </div>
        <div class="status-item">
          <strong>Message:</strong>
          <span>{{ status.message }}</span>
        </div>
        <div class="status-item">
          <strong>Version:</strong>
          <span>{{ status.version }}</span>
        </div>
      </div>
      <button @click="fetchStatus" class="refresh-btn">Refresh Status</button>
    </div>
  </div>
</template>

<style scoped>
.server-status {
  background: white;
  border-radius: 8px;
  padding: 2rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

h2 {
  margin-top: 0;
  color: #2c3e50;
}

.loading {
  text-align: center;
  padding: 2rem;
  color: #666;
}

.error {
  background: #fee;
  border: 1px solid #fcc;
  border-radius: 4px;
  padding: 1rem;
  color: #c33;
}

.error button {
  margin-top: 1rem;
}

.status-card {
  background: #f5f5f5;
  border-radius: 4px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.status-item:not(:last-child) {
  border-bottom: 1px solid #ddd;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: bold;
}

.badge.online {
  background: #4caf50;
  color: white;
}

.badge.offline {
  background: #f44336;
  color: white;
}

button {
  background: #42b983;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  transition: background 0.3s;
}

button:hover {
  background: #359268;
}

.refresh-btn {
  width: 100%;
}
</style>
