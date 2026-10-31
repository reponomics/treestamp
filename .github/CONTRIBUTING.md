# Contributing

Discuss ordinary bugs and proposed changes in [reponomics/treestamp issues](https://github.com/reponomics/treestamp/issues). Follow the [code of conduct](CODE_OF_CONDUCT.md) and use [private reporting](SECURITY.md) for vulnerabilities.

## Set up

Use Python 3.11+ and the uv version pinned in `.tool-versions` to manage a virtual environment named `venv`. Install uv through its official standalone installer or your system package manager; do not bootstrap it through an outdated pip. JavaScript checks use the Node version in `.nvmrc`, selected through nvm. The frontend has no npm installation or bundling step.

```bash
make venv
make install
nvm install
nvm use
make ci web-ci docs-check
```

`make install` synchronizes both packages, build tools, and all test dependencies from the committed `uv.lock`. It fails if the dependency declarations have changed without updating the lock. `make web-install` and `make web-browser-install` are aliases for the same workspace setup. Browser tests also require Chromium or an installed Chrome:

```bash
venv/bin/playwright install chromium
make web-browser-test
```

To use Chrome, pass `BROWSER_FLAGS="--browser-channel chrome"`. On Linux, Playwright's `install --with-deps chromium` can install the required system dependencies. See [web/README.md](../web/README.md) to run the application locally.

The Makefile uses POSIX paths. On Windows, set `UV_PROJECT_ENVIRONMENT=venv`, then run `uv sync --locked --all-packages --all-extras --no-install-workspace --no-build` followed by `uv sync --locked --all-packages --all-extras --no-build-isolation`. Activate `venv` and invoke Python tools directly; the [CI workflow](workflows/ci.yml) contains the Windows regression and installed-package commands.

## Dependencies

Prefer the standard library and existing dependencies. Propose a new dependency in the pull request that adds it, explaining why it is needed. It must be actively maintained, publish wheels for the supported Python versions and platforms, and have a license in the allowlist of the [dependency scan](workflows/osv-scanner.yml), which checks every locked package. Any other license, including copyleft licenses, needs the maintainer's review and a recorded exception in `osv-scanner.toml`. A dependency found to violate this is replaced or removed before the next release. Declare the core package's runtime dependencies in `pyproject.toml`, the hosted editor's in `web/pyproject.toml`, and development tools in the `dev` extras.

Dependencies are obtained from PyPI through uv. For intentional dependency changes, edit the appropriate `pyproject.toml`, run `uv lock`, and commit the lock with the declarations. Use `make lock-update` for a deliberate full dependency refresh, or `uv lock --upgrade-package NAME` for a targeted update. Re-run `make install` and the relevant checks. The lock manages repository development and deployment; the published package retains compatible dependency ranges.

[Dependabot](dependabot.yml) proposes updates and OSV-Scanner checks the locked dependencies for known vulnerabilities. [MAINTENANCE.md](../docs/MAINTENANCE.md#dependencies-and-toolchain) covers reviewing these updates and the pinned toolchain versions.

## Tests for changes

Treestamp maintains a high level of code coverage. Changes introduced in a PR should avoid reducing coverage by more than 1%, if at all, and a strict threshold of 90% coverage is enforced. Non-trivial changes must add or update automated tests in the same pull request. High-impact changes must be accompanied by thorough testing.

Tests belong in the suite that covers the changed area, described under [Check changes](#check-changes), and should assert the changed behavior itself, not only exercise the code (test coverage as well as code coverage). Changes that leave behavior unchanged, such as documentation, refactoring already covered by existing tests, and dependency updates that pass the suites, need no new tests. Avoid brittle tests that depend on specific string literals, and, especially when working with coding agents, avoid excessive testing that provides no durable benefit.

## Check changes

Run focused tests during implementation and the relevant complete checks before review: `make ci`, `make web-ci`, `make web-browser-test`, and `make docs-check`. For distribution changes, also run `make build metadata-check distribution-check`. See [MAINTENANCE.md](../docs/MAINTENANCE.md) for release and deployment checks.

The core suite in `tests/` covers the CLI, document parsing and writing, Git snapshots, tree maintenance, and the terminal editor through headless journeys. The hosted editor's suite in `web/tests/` covers its API, GitHub client, cache, and limits against a fake GitHub API served from a local checkout; `web/tests/browser/` drives the page in Chromium, and `web/tests/js/` tests the page's pure logic with Node's test runner. `make ci` and `make web-ci` fail if either suite's coverage falls below 90%.

CI runs on every pull request to `main` and every push to `main`. The [CI workflow](workflows/ci.yml) runs the core suite on Linux and Windows with Python 3.11 and 3.12, the complete quality gates and distribution checks on Linux with Python 3.11, and the hosted editor's quality gates, browser suite, and container health probe. [MAINTENANCE.md](../docs/MAINTENANCE.md#repository-and-release-setup) lists the checks required before merging. Each job appears as a check on the pull request; a failing check's log shows pytest's summary of failed tests and assertions, the coverage report with missed lines, or the README diff from `treestamp check`.

Install development hooks with `venv/bin/pre-commit install`. They run lint and formatting, strict type checks, Python tests selected from changed files, and the README tree check. `make pre-commit-check` runs them over all files and may apply formatting fixes. A change affecting shared behavior still needs the relevant complete suite.

Stage source additions, deletions, and moves before running `venv/bin/treestamp update README.md`; inspect and stage the resulting README separately. Treestamp and its hooks never stage or commit files. `make integration-check` verifies the staged tree against the README. After committing a candidate, `make hook-check` verifies hooks installed from that HEAD; it does not cover uncommitted changes.

Preserve exact path identity, frozen editing snapshots, and draft recovery on failed operations. Keep Markdown prose unwrapped. Include release notes when a change requires users to modify their documents or workflows. Update the documentation a change affects in the same pull request, and treat errors in the documentation as bugs. Automated browser tests do not replace a manual check of keyboard operation, terminal display, or clipboard behavior.
