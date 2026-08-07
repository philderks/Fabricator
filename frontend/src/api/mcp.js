import { get, put, post, del } from './client'

// Mirrors src/api/auth.js: relative paths through the shared client (same-origin
// cookie is sent by default — no credentials or absolute-URL handling here).

export function getMcp() {
  return get('/api/integrations/mcp')
}

export function setMcpEnabled(enabled) {
  return put('/api/integrations/mcp', { enabled })
}

export function createMcpToken(name, scope) {
  return post('/api/integrations/mcp/tokens', { name, scope })
}

export function deleteMcpToken(id) {
  return del(`/api/integrations/mcp/tokens/${encodeURIComponent(id)}`)
}
