# fabricator-mcp

An MCP server for the [Fabricator](https://github.com/philderks/Fabricator) Minecraft panel. It
runs on **your** machine, next to your MCP client, and talks to your panel over its HTTP API using
an API token you mint in the panel's **Integrations** page.

It is built for one job: working out why a modpack server is crashing. Read the log, see what is
installed, check a mod against Modrinth, remove or update it, restart.

> **This package is not a security boundary.** What a token may do is decided and enforced by the
> panel, against the token, on the server side. The tool set here is a curation layer: it is
> narrower than what the token can reach, and it stays honest about the difference.

## Requirements

- The panel, reachable from this machine, with **MCP access enabled** under *Integrations*.
- An API token. **`read` is the recommended default** — it cannot change anything. Use `manage`
  only when you want the assistant to be able to act.

## Configuration

Two environment variables, set by your MCP client on the process it spawns:

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `FABRICATOR_URL` | no | `http://127.0.0.1:5000` | Base URL of the panel |
| `FABRICATOR_TOKEN` | **yes** | — | The API token from the Integrations page |

The token is **never** read from the command line. `argv` is visible to every process on the
machine and lands in shell history; a spawned process's environment is neither. The file holding
your client configuration contains the token in plain text — treat it like a password.

Connect instructions for a specific client ship with the documentation commit.

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
