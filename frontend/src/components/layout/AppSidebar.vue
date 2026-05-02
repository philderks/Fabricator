<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ServerSwitcher from './ServerSwitcher.vue'
import { version as appVersion } from '../../../package.json'

const route = useRoute()
const serverId = computed(() => route.params.id)

const navItems = [
  { name: 'ServerOverview', label: 'Overview', icon: 'overview' },
  { name: 'ServerConsole',  label: 'Console',  icon: 'console'  },
  { name: 'ServerMods',     label: 'Mods',     icon: 'mods'     },
  { name: 'ServerFiles',    label: 'Files',    icon: 'files'    },
  { name: 'ServerSettings', label: 'Settings', icon: 'settings' }
]
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__logo">
      <img
        class="app-sidebar__logo-img"
        src="/favicon.svg"
        alt=""
        width="24"
        height="24"
        aria-hidden="true"
      />
      <span class="app-sidebar__brand">Fabricator</span>
    </div>

    <ServerSwitcher />

    <nav class="app-sidebar__nav" aria-label="Server navigation">
      <router-link
        v-for="item in navItems"
        :key="item.name"
        :to="{ name: item.name, params: { id: serverId } }"
        class="app-sidebar__nav-item"
        active-class="is-active"
      >
        <svg class="app-sidebar__nav-icon" width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <template v-if="item.icon === 'overview'">
            <rect x="1.5" y="1.5" width="4.5" height="4.5" rx="1"/>
            <rect x="9" y="1.5" width="4.5" height="4.5" rx="1"/>
            <rect x="1.5" y="9" width="4.5" height="4.5" rx="1"/>
            <rect x="9" y="9" width="4.5" height="4.5" rx="1"/>
          </template>
          <template v-else-if="item.icon === 'console'">
            <rect x="1" y="2" width="13" height="11" rx="1.5"/>
            <path d="M4 5.5l2.5 2L4 9.5"/>
            <path d="M8 9.5h3"/>
          </template>
          <template v-else-if="item.icon === 'mods'">
            <path d="M7.5 1L13 4.5v6L7.5 14 2 10.5v-6L7.5 1z"/>
            <path d="M7.5 1v13M2 4.5l5.5 3.5 5.5-3.5"/>
          </template>
          <template v-else-if="item.icon === 'files'">
            <path d="M2 3.5A1.5 1.5 0 013.5 2h3l1.5 2H12a1.5 1.5 0 011.5 1.5v7A1.5 1.5 0 0112 14H3.5A1.5 1.5 0 012 12.5v-9z"/>
          </template>
          <template v-else-if="item.icon === 'settings'">
            <circle cx="7.5" cy="7.5" r="2"/>
            <path d="M7.5 1v1.5M7.5 12.5V14M1 7.5h1.5M12.5 7.5H14M3 3l1 1M11 11l1 1M11 3l-1 1M3 12l1-1" stroke-linecap="round"/>
          </template>
        </svg>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <div class="app-sidebar__footer">
      <span class="app-sidebar__version">Fabricator v{{ appVersion }}</span>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-3);
  border-bottom: 1px solid var(--border-color);
}

.app-sidebar__logo-img {
  flex-shrink: 0;
  display: block;
}

.app-sidebar__brand {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.app-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2);
  flex: 1;
}

.app-sidebar__nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: var(--text-sm);
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}

.app-sidebar__nav-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.app-sidebar__nav-item.is-active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.app-sidebar__nav-item.is-active .app-sidebar__nav-icon {
  color: var(--primary);
}

.app-sidebar__nav-icon {
  flex-shrink: 0;
}

.app-sidebar__footer {
  padding: var(--space-3);
  border-top: 1px solid var(--border-color);
}

.app-sidebar__version {
  font-size: var(--text-xs);
  color: var(--text-disabled);
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}
</style>
