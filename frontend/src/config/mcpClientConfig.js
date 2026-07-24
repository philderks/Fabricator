/**
 * The generated MCP client configuration — the SINGLE place its shape lives.
 *
 * PLACEHOLDER: `command`/`args` depend on Unit B's distribution channel, which
 * is not decided yet. When it is, change them HERE and the rendered config
 * updates everywhere. The token always rides in `env`, never in `args`; the
 * panel URL comes from the editable field in the UI.
 */
export const MCP_CLIENT_LAUNCH = {
  command: 'fabricator-mcp', // PLACEHOLDER — set by Unit B distribution
  args: [] // PLACEHOLDER — set by Unit B distribution
}

export const MCP_TOKEN_PLACEHOLDER = 'YOUR_TOKEN_HERE'

export function buildMcpClientConfig({ url, token } = {}) {
  return {
    mcpServers: {
      fabricator: {
        command: MCP_CLIENT_LAUNCH.command,
        args: [...MCP_CLIENT_LAUNCH.args],
        env: {
          FABRICATOR_URL: url || '',
          FABRICATOR_TOKEN: token || MCP_TOKEN_PLACEHOLDER
        }
      }
    }
  }
}
