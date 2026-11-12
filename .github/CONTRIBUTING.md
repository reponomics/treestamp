# Contributing

Discuss ordinary bugs and proposed changes in the project's [issues section](https://github.com/reponomics/treestamp/issues). For non-trivial changes, propose the change in an issue before submitting a Pull Request. Follow the [code of conduct](CODE_OF_CONDUCT.md) and use [private reporting](SECURITY.md) for vulnerabilities.

## Git

### Commit Messages

Prefer to use [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) when committing code for this repo.

### Commit Signing

Please ensure that your commits are signed and appear as "Verified" on GitHub. See GitHub [docs](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) for guidance. This is required and enforced on Pull Requests.

### Commit Signoff - DCO

By contributing to this project, you must agree to the [Developer Certificate of Origin (DCO) version 1.1](./DCO.txt). This is a confirmation that you have the right to submit the code changes that you propose. To make this explicit, please include a `Signed-off-by: NAME <EMAIL ADDRESS>` trailer in your commits, which you can do simpy by adding the `--signoff` flag (or `-s`) when running `git commit`; i.e., `git commit --signoff`. Unlike commit signatures, it's acceptable to omit this from some commits, and it is not enforced by CI.

## Set up

Use Python 3.11+ and the uv version pinned in `.tool-versions` to manage a virtual environment named `venv`. Install uv through its official standalone installer or your system package manager; do not bootstrap it through an outdated pip. JavaScript checks use the Node version in `.nvmrc`, selected through nvm. The frontend has no npm installation or bundling step.

```bash
make venv
make install
nvm install
nvm use
make ci web-ci docs-check
```

`make install` synchronizes both packages, build tools, and all test dependencies from the committed `uv.lock`. It fails if the dependency declarations have changed without updating the lock. `make web-install` and `make web-browser-install` are aliases for the same workspace setup. See the [testing guide](../docs/testing.md#suites-and-commands) for browser installation and test commands, and [web/README.md](../web/README.md) to run the application locally.

The Makefile uses POSIX paths. On Windows, set `UV_PROJECT_ENVIRONMENT=venv`, then run `uv sync --locked --all-packages --all-extras --no-install-workspace --no-build` followed by `uv sync --locked --all-packages --all-extras --no-build-isolation`. Activate `venv` and invoke Python tools directly; the [CI workflow](workflows/ci.yml) contains the Windows regression and installed-package commands.

## Dependencies

Prefer the standard library and existing dependencies. Propose a new dependency in the pull request that adds it, explaining why it is needed. It must be actively maintained, publish wheels for the supported Python versions and platforms, and have a license in the allowlist of the [dependency scan](workflows/osv-scanner.yml), which checks every locked package. Any other license, including copyleft licenses, needs the maintainer's review and a recorded exception in `osv-scanner.toml`. A dependency found to violate this is replaced or removed before the next release. Declare the core package's runtime dependencies in `pyproject.toml`, the hosted editor's in `web/pyproject.toml`, and development tools in the `dev` extras.

Dependencies are obtained from PyPI through uv. For intentional dependency changes, edit the appropriate `pyproject.toml`, run `uv lock`, and commit the lock with the declarations. Use `make lock-update` for a deliberate full dependency refresh, or `uv lock --upgrade-package NAME` for a targeted update. Re-run `make install` and the relevant checks. The lock manages repository development and deployment; the published package retains compatible dependency ranges.

[Dependabot](dependabot.yml) proposes updates and OSV-Scanner checks the locked dependencies for known vulnerabilities. [MAINTENANCE.md](../docs/MAINTENANCE.md#dependencies-and-toolchain) covers reviewing these updates and the pinned toolchain versions.

## Tests for changes

Non-trivial changes must add or update behavioral tests in the same pull request. Both Python suites enforce a **95% coverage minimum**. The [testing guide](../docs/testing.md) defines the full policy, suite responsibilities, coverage boundaries, and current verification status.

## Check changes

Run focused tests during implementation and the relevant complete checks before review, following the [testing guide](../docs/testing.md#suites-and-commands). It also covers [CI and local hooks](../docs/testing.md#ci-and-local-hooks); use the [maintenance runbook](../docs/MAINTENANCE.md#validate-and-build) for release and installed-package checks.

Stage source additions, deletions, and moves before running `venv/bin/treestamp update README.md`; inspect and stage the resulting README separately. Treestamp and its hooks never stage or commit files. `make integration-check` verifies the staged tree against the README. After committing a candidate, `make hook-check` verifies hooks installed from that HEAD; it does not cover uncommitted changes.

Preserve exact path identity, frozen editing snapshots, and draft recovery on failed operations. Keep Markdown prose unwrapped. Include release notes when a change requires users to modify their documents or workflows. Update the documentation a change affects in the same pull request, and treat errors in the documentation as bugs.
