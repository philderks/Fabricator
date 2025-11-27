<script setup>
defineProps({
  activities: {
    type: Array,
    required: true
  }
})
</script>

<template>
  <div class="activity-list">
    <div v-for="(activity, i) in activities" :key="i" class="activity-item">
      <div class="activity-dot" :class="activity.type"></div>
      <div class="activity-content">
        <div class="activity-text">
          <span v-if="activity.type === 'player_join'">
            <strong>{{ activity.user }}</strong> joined the server
          </span>
          <span v-else-if="activity.type === 'player_leave'">
            <strong>{{ activity.user }}</strong> left the server
          </span>
          <span v-else-if="activity.type === 'mod_install'">
            Installed mod <strong>{{ activity.mod }}</strong>
          </span>
          <span v-else-if="activity.type === 'mod_update'">
            Updated mod <strong>{{ activity.mod }}</strong>
          </span>
          <span v-else>Server started</span>
        </div>
        <div class="activity-time">{{ activity.time }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.activity-item {
  display: flex;
  gap: 1rem;
  padding: 0.875rem 0;
  border-bottom: 1px solid var(--border-color);
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 0.5rem;
  flex-shrink: 0;
}

.activity-dot.player_join {
  background: var(--success);
}

.activity-dot.player_leave {
  background: var(--text-disabled);
}

.activity-dot.mod_install,
.activity-dot.mod_update {
  background: var(--primary);
}

.activity-dot.server_start {
  background: var(--success);
}

.activity-content {
  flex: 1;
}

.activity-text {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin-bottom: 0.25rem;
}

.activity-text strong {
  color: var(--text-primary);
  font-weight: 600;
}

.activity-time {
  color: var(--text-disabled);
  font-size: 0.8125rem;
}
</style>
