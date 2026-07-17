# Contributing to Fabricator

Bug reports and pull requests are welcome. For larger changes, please open an issue first to discuss what you would like to change.

## Scope

Fabricator is a self-hosted web dashboard for managing modded Minecraft servers
primarily on Linux and Docker, with Modrinth mod management built in. It targets people running
always-on servers on their own hardware or a VPS, and it stays deliberately
lightweight.

## Before you write code

**Bugs.** [Open a bug report](https://github.com/philderks/Fabricator/issues/new?template=bug_report.yml).
If the fix is small and self-contained, feel free to open a PR alongside it.
Keep it to one fix, and include a test where the bug is testable.

**Changing something that already exists.** A unit that should be different, a
confusing label, a wrong default, a value that's too coarse to be useful.
[Open an improvement](https://github.com/philderks/Fabricator/issues/new?template=improvement.yml).
These are welcome, and small ones are still worth filing. If you already know
what the change should be and it's contained, a PR alongside the issue is fine.

**Adding something new.**
[Open a feature request](https://github.com/philderks/Fabricator/issues/new?template=feature_request.yml)
and wait for a reply before writing code. Describe the problem you're running
into, not only the solution you have in mind. New capability gets weighed against
the roadmap and the scope above, so an agreed issue first means you don't spend
an evening on something we end up declining.

**Refactors, directory restructures, build tooling, CI, packaging.**
[Open an issue first](https://github.com/philderks/Fabricator/issues/new?template=refactor.yml),
always, and wait for agreement. Unsolicited restructuring pull requests are
likely to be declined or only partially taken, however good the work is. This
isn't about quality. Structural changes have consequences for the installer, the
release pipeline, the packaged Docker image, and existing in-place updates that
aren't visible in the diff.

**Security vulnerabilities.** Don't open a public issue or a pull request.
Report privately via
[GitHub Security Advisories](https://github.com/philderks/Fabricator/security/advisories/new)
or email contact@fabricator.site.

**Documentation.** Open a PR directly. Typos, wrong commands, and stale
instructions are always welcome.

If you're not sure which of these applies, open whichever fits best and we'll
sort it out. Filing in the wrong place is not a problem.

# Pull requests

- One concern per PR. Separate PRs are easier to review and faster to merge than
  one large one.
- Do not mix formatting or refactoring into a functional change.
- Explain what problem the change solves in the description, and link the issue
  if there is one.
- Test what you claim your code does. Screenshots help for UI changes.

## Project layout
```
backend/      Flask app: blueprints, server process registry, installers, Modrinth client
frontend/     Vue 3 + Vite single-page UI
tools/        install.sh, update.sh, CLI, build helpers
tests/        pytest suite for the backend
run.py        Process entrypoint
```

## Development setup

Requires Python 3.11+ and Node.js 20.x.

Backend:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

The API runs on `http://localhost:5000`.

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:3000` with hot reload and proxies `/api`
to the backend on port 5000. Use this for frontend work.

`npm run build` is only needed if you want `run.py` to serve the built UI
directly, which is how packaged installs work.

Environment variables are documented in `.env.example`. In development the app
binds to loopback only.

## Tests

```bash
pytest
```

pytest is already in `requirements.txt`, so there is no separate dev install.
New behavior should come with a test. Bug fixes should come with a test that
fails before the fix.

## Contributor License Agreement

By opening a pull request, you agree to the following:

1. **You have the right to submit the contribution.** The work is your own and you are legally entitled to grant the rights described below.
2. **You grant Philipp Noél Derks and Linus Sommermeyer, and their respective successors and assigns, a perpetual, worldwide, non-exclusive, royalty-free license** to use, reproduce, modify, sublicense, and distribute your contribution under any license, including commercial licenses, without further obligation to you.
3. **Your contribution is submitted under AGPL-3.0.** All contributions to this repository are licensed to the public under the [GNU Affero General Public License v3.0](LICENSE).
4. **You understand that your contribution may be used commercially.** Philipp Noél Derks and Linus Sommermeyer, and their respective successors and assigns, reserve the right to offer Fabricator under additional or alternative licenses, including for commercial purposes.

When you open a pull request, the CLA Assistant bot will ask you to confirm acceptance of these terms. Your agreement is recorded against your GitHub account, and you only need to sign once.
