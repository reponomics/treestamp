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

Keep runtime dependencies few. The core package depends only on Textual; the hosted editor adds FastAPI, Uvicorn, HTTPX, PyJWT, and certifi. Prefer the standard library or an existing dependency. Propose a new dependency in the pull request that needs it, explaining why. It should be actively maintained and widely used, published on PyPI with wheels for the supported platforms, and licensed compatibly with MIT. The frontend uses no npm packages.

Dependencies are obtained from PyPI with uv. Direct dependencies and their compatible ranges are declared in `pyproject.toml` and `web/pyproject.toml`; `uv.lock` records the exact versions and hashes used for development, CI, release builds, and the container image. GitHub Actions are pinned to commit SHAs, and the container base image is pinned by digest.

Dependabot proposes weekly updates for Python packages, GitHub Actions, and the container image, and opens security updates when advisories are published. The OSV scanner workflow checks the locked Python dependencies on each push to `main` and weekly. [MAINTENANCE.md](../MAINTENANCE.md#dependency-and-installer-maintenance) describes how updates are reviewed.

For intentional dependency changes, edit the appropriate `pyproject.toml`, run `uv lock`, and commit the lock with the declarations. Use `make lock-update` for a deliberate full dependency refresh, or `uv lock --upgrade-package NAME` for a targeted update. Re-run `make install` and the relevant checks. The lock manages repository development and deployment; the published package retains compatible dependency ranges.

## Check changes

Run focused tests during implementation and the relevant complete checks before review: `make ci`, `make web-ci`, `make web-browser-test`, and `make docs-check`. For distribution changes, also run `make build metadata-check distribution-check`. See [MAINTENANCE.md](../MAINTENANCE.md) for release and deployment checks.

Install development hooks with `venv/bin/pre-commit install`. They run lint and formatting, strict type checks, Python tests selected from changed files, and the README tree check. `make pre-commit-check` runs them over all files and may apply formatting fixes. A change affecting shared behavior still needs the relevant complete suite.

Stage source additions, deletions, and moves before running `venv/bin/treestamp update README.md`; inspect and stage the resulting README separately. Treestamp and its hooks never stage or commit files. `make integration-check` verifies the staged tree against the README. After committing a candidate, `make hook-check` verifies hooks installed from that HEAD; it does not cover uncommitted changes.

Preserve exact path identity, frozen editing snapshots, and draft recovery on failed operations. Keep Markdown prose unwrapped. Include release notes when a change requires users to modify their documents or workflows. Automated browser tests do not replace a manual check of keyboard operation, terminal display, or clipboard behavior.
