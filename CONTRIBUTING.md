# Contributing to Fabricator

Bug reports and pull requests are welcome. For larger changes, please open an issue first to discuss what you would like to change.

## Contributor License Agreement

By opening a pull request, you agree to the following:

1. **You have the right to submit the contribution.** The work is your own and you are legally entitled to grant the rights described below.
2. **You grant Philipp Noél Derks and Linus Sommermeyer, and their respective successors and assigns, a perpetual, worldwide, non-exclusive, royalty-free license** to use, reproduce, modify, sublicense, and distribute your contribution under any license, including commercial licenses, without further obligation to you.
3. **Your contribution is submitted under AGPL-3.0.** All contributions to this repository are licensed to the public under the [GNU Affero General Public License v3.0](LICENSE).
4. **You understand that your contribution may be used commercially.** Philipp Noél Derks and Linus Sommermeyer, and their respective successors and assigns, reserve the right to offer Fabricator under additional or alternative licenses, including for commercial purposes.

When you open a pull request, the CLA Assistant bot will ask you to confirm acceptance of these terms. Your agreement is recorded against your GitHub account, and you only need to sign once.

## Development Setup

The frontend is Vue 3 + Vite in `/frontend`. The backend is Flask with blueprints under `/backend`; the process entrypoint is `run.py`. HTTP API details are in [API_DOCS.md](API_DOCS.md).

Both halves run without the installer for local development. See the [manual installation steps](README.md#quick-start) in the README for the exact commands.
