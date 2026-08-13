# fabricator-mcp

> **Beta.** Young, and the way the client is configured may change between releases.

An MCP server for the [Fabricator](https://github.com/philderks/Fabricator) Minecraft panel. It
runs on **your** machine, next to your MCP client, and talks to your panel over its HTTP API using
an API token you mint in the panel's **Settings**, under *Model Context Protocol*.

It is built for one job: working out why a modpack server is crashing. Read the log, see what is
installed, check a mod against Modrinth, remove or update it, restart.

> **This package is not a security boundary.** What a token may do is decided and enforced by the
> panel, against the token, on the server side. The tool set here is a curation layer: it is
> narrower than what the token can reach, and it stays honest about the difference.

## Requirements

- The panel, reachable from this machine, with **MCP access enabled** in *Settings* → *Model
  Context Protocol*.
- An API token. **`read` is the recommended default** — it cannot change anything. Use `manage`
  only when you want the assistant to be able to act.
- **[`uv`](https://docs.astral.sh/uv/) installed and on your `PATH`.** This is the one hard
  prerequisite, and it is not bundled with any MCP client. If `uv` is missing, your client will
  report the Fabricator server as **failing to launch or disconnecting at startup** — it looks
  like a broken server, not like a panel or token problem, because the process never starts.
  Installing `uv` fixes it.

## Connecting a client

Put this in your client's MCP server configuration (for Claude Desktop, `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "fabricator": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/philderks/Fabricator@dev#subdirectory=mcp",
        "fabricator-mcp"
      ],
      "env": {
        "FABRICATOR_URL": "http://127.0.0.1:5000",
        "FABRICATOR_TOKEN": "YOUR_TOKEN_HERE"
      }
    }
  }
}
```

The panel generates this block for you, with the URL and token filled in, in **Settings** →
*Model Context Protocol*.

> The package is installed straight from the repository because it is not published to PyPI yet.
> When it is, `command` and `args` become `"uvx"` and `["fabricator-mcp"]`, and nothing else
> changes. Those two values are the entire launch channel; they live here and in
> `frontend/src/config/mcpClientConfig.js`.

## What the assistant can do

The token's scope decides this, and the **panel** enforces it — not this package.

| Scope | What it reaches |
|---|---|
| `read` | List servers and their status · read console output and crash logs · list installed mods and identify them against Modrinth by file hash · CPU and memory use · Java version checks · install progress and failure reasons · search Modrinth and check whether a mod has a build for your Minecraft version and loader |
| `manage` | Everything above, plus: start / stop / restart a server · install or update one mod by Modrinth project id · delete installed mod jars |

**`read` is the documented default.** It answers every diagnostic question and cannot change
anything on your server.

Whatever the scope, a large part of the panel is refused to **every** token: the console, file
reading and writing, server settings, creating or deleting servers, Java installation, the
updater, backups and snapshot restore, world import, and all player administration including the
player lists. Those refusals happen in the panel, and this package surfaces them as they are
rather than hiding the tools.

### Known limitation: mods in subfolders

Only jars sitting **directly** in a server's `mods` folder are listed, and only those can be
removed. A jar inside a subfolder is invisible to the listing and cannot be deleted with
`remove_mods` — manage it through the panel UI instead. The tools say so rather than failing
opaquely.

## Security notes

- **Server logs contain text written by mods and by players.** Anything that can print to the
  server console — a mod, a player's chat message, a nickname, the MOTD — ends up in what the
  assistant reads. A `manage` token lets an assistant act on what it reads there. Prefer a `read`
  token unless you specifically want it to be able to change things.
- **The token sits in plain text in your MCP client's configuration file.** Treat that file like a
  password: anyone who can read it can use the token.
- Tokens do not expire. Revoke any you no longer use, from the same Settings panel.
- Turning MCP access off in the panel makes existing tokens stop working immediately without
  deleting them.

## Configuration

Two environment variables, set by your MCP client on the process it spawns:

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `FABRICATOR_URL` | no | `http://127.0.0.1:5000` | Base URL of the panel |
| `FABRICATOR_TOKEN` | **yes** | — | The API token from the panel's Settings |

The token is **never** read from the command line. `argv` is visible to every process on the
machine and lands in shell history; a spawned process's environment is neither.

## Development

The package is a **dependency island**: its own `pyproject.toml`, its own lockfile, its own
interpreter pin, resolved and run entirely separately from the panel. The panel's
`requirements.txt` is not involved and does not change.

```bash
cd mcp
uv sync                 # create .venv from uv.lock, provisioning CPython 3.11
uv run pytest           # run this package's suite
```

CI, and anyone who wants the exact recorded environment:

```bash
cd mcp
uv sync --frozen        # fails if uv.lock has drifted from pyproject.toml
uv run pytest -q
```

Changing a dependency is the only thing that moves the recipe, and both files are committed
together:

```bash
cd mcp
uv add "mcp>=1.28"
git add pyproject.toml uv.lock
```

**The committed recipe is `pyproject.toml` + `uv.lock` + `.python-version`.** A stand without a
committed recipe is a scratchpad ghost; do not regenerate the lock as a side effect of unrelated
work.

### Isolation from the panel suite

Four independent mechanisms keep this suite and the panel's from touching each other:

1. **Separate resolution** — this `pyproject.toml` + `uv.lock`; the panel keeps
   `requirements.txt`. Neither references the other.
2. **Separate environment** — `mcp/.venv`. The panel's environment has no `mcp`/`httpx`; this one
   has no Flask.
3. **Separate pytest rootdir** — the `[tool.pytest.ini_options]` table in `pyproject.toml` stops
   pytest's upward search here, so a run in `mcp/` never loads the panel's `conftest.py`; the
   panel's `pytest.ini` sets `testpaths = tests` and `norecursedirs = mcp` so a run at the repo
   root never descends into this directory.
4. **Separate CI job** — path-scoped to `mcp/**`, with its own working directory.

**Do not add a `[tool.uv.workspace]` to the repository root.** A workspace would merge the two
lockfiles and environments and destroy the island.

### Testing rules

- **No test may reach the network.** `tests/conftest.py` installs an autouse guard that turns an
  un-mocked request into a failed test. Drive the client with `httpx.MockTransport`.
- The tool-to-route mapping is a data table, and a test asserts it is a subset of the routes the
  panel permits a token. If the panel's classification moves, that test goes red on purpose.

## Licence

AGPL-3.0-only, inherited from the Fabricator repository.
