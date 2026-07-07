# Contributing to Fabricator

Bug reports and pull requests are welcome. For larger changes, please open an issue first to discuss what you would like to change.

## Contributor License Agreement

By submitting a pull request, you agree to the following:

1. **You have the right to submit the contribution.** The work is your own and you are legally entitled to grant the rights described below.

2. **You grant Philipp Noél Derks and Linus Sommermeyer a perpetual, worldwide, non-exclusive, royalty-free license** to use, reproduce, modify, sublicense, and distribute your contribution under any license — including commercial licenses — without further obligation to you.

3. **Your contribution is submitted under AGPL-3.0.** All contributions to this repository are licensed to the public under the [GNU Affero General Public License v3.0](LICENSE).

4. **You understand that your contribution may be used commercially.** Philipp Noél Derks and Linus Sommermeyer reserve the right to offer Fabricator under additional or alternative licenses, including for commercial purposes.

By merging a pull request, the contributor confirms acceptance of these terms.

## Development Setup

The frontend is Vue 3 + Vite in `apps/frontend`. The backend is Flask with blueprints under `apps/backend`; the process entrypoint is root-level `run.py`. HTTP API details are in [API_DOCS.md](API_DOCS.md). Both halves can be run without the installer for local development.
