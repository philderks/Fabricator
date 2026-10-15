import { createI18n } from 'vue-i18n'
import en from './locales/en.json'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en }
})

// For stores, utils and other plain modules, which have no component to call
// useI18n() from. Components use $t in templates and this same `t` in scripts.
export const { t, te } = i18n.global

/** "a, b and c" (or "a, b or c" with type 'disjunction') in the UI language. */
export const formatList = (items, type = 'conjunction') =>
  new Intl.ListFormat(i18n.global.locale.value, { type }).format(items)
