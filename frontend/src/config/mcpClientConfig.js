/**
 * The generated MCP client configuration — the SINGLE place its shape lives.
 *
 * The launch channel is these two constants and nothing else. Today the server
 * is installed straight from the repository, because the package is not on PyPI
 * yet. When it is published, the swap is:
 *
 *   command: 'uvx'
 *   args: ['fabricator-mcp']
 *
 * and nothing else in the panel or the package changes. Keep the same wording
 * in mcp/README.md, which is the only other place this pair is written down.
 *
 * The token always rides in `env`, never in `args`: a command line is readable
 * by every process on the machine and lands in shell history. The panel URL
 * comes from the editable field in the UI.
 */
export const MCP_CLIENT_LAUNCH = {
  command: 'uvx',
  args: [
    '--from',
    'git+https://github.com/philderks/Fabricator@dev#subdirectory=mcp',
    'fabricator-mcp'
  ]
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
