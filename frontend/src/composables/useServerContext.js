import { provide, inject } from 'vue'

const SERVER_CONTEXT_KEY = Symbol('serverContext')

export function provideServerContext(ctx) {
  provide(SERVER_CONTEXT_KEY, ctx)
}

export function useServerContext() {
  const ctx = inject(SERVER_CONTEXT_KEY)
  if (!ctx) {
    throw new Error('useServerContext() must be called inside <ServerLayout>')
  }
  return ctx
}
