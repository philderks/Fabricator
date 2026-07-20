<script setup>
defineProps({
  iconUrl: {
    type: String,
    default: null
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  },
  meta: {
    type: String,
    default: ''
  },
  selected: {
    type: Boolean,
    default: false
  }
})
</script>

<template>
  <article class="search-result-card" :class="{ 'is-selected': selected }">
    <div v-if="$slots.lead" class="search-result-card__lead">
      <slot name="lead" />
    </div>
    <div class="search-result-card__icon">
      <img v-if="iconUrl" :src="iconUrl" :alt="title" loading="lazy" />
      <span v-else class="search-result-card__icon-placeholder" aria-hidden="true">
        {{ title.charAt(0).toUpperCase() }}
      </span>
    </div>
    <div class="search-result-card__body">
      <h3 class="search-result-card__title">{{ title }}</h3>
      <p v-if="description" class="search-result-card__description">{{ description }}</p>
      <p v-if="meta" class="search-result-card__meta">{{ meta }}</p>
    </div>
    <div class="search-result-card__action">
      <slot />
    </div>
  </article>
</template>

<style scoped>
.search-result-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  transition: border-color 0.15s ease;
}

.search-result-card:hover {
  border-color: var(--border-hover);
}

.search-result-card.is-selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--primary) 20%, transparent);
}

/* Optional leading control (e.g. the installed list's bulk-select checkbox).
   Absent in the browse modal, which renders no lead slot. */
.search-result-card__lead {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.search-result-card__icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-result-card__icon img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.search-result-card__icon-placeholder {
  font-size: var(--text-md);
  font-weight: 700;
  color: var(--text-muted);
}

.search-result-card__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.search-result-card__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-card__description {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: var(--leading-normal);
}

.search-result-card__meta {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--text-disabled);
}

.search-result-card__action {
  flex-shrink: 0;
}

@media (max-width: 600px) {
  .search-result-card {
    flex-direction: column;
    align-items: stretch;
  }

  .search-result-card__icon {
    align-self: flex-start;
  }

  .search-result-card__action {
    align-self: stretch;
  }
}
</style>
