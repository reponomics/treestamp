# Contributing

Discuss ordinary bugs and proposed changes in [reponomics/treestamp issues](https://github.com/reponomics/treestamp/issues). Follow the [code of conduct](CODE_OF_CONDUCT.md) and use [private reporting](SECURITY.md) for vulnerabilities.

## Set up

Use Python 3.11+ and a virtual environment named `venv`. JavaScript checks use the Node version in `.nvmrc`, selected through nvm. The frontend has no npm installation or bundling step.

```bash
make venv
make install web-install
nvm install
nvm use
make ci web-ci docs-check
```

`make install` installs the core package and development dependencies. `make web-install` adds the hosted package and its development dependencies; both are needed for the repository's complete checks. Browser tests also require Chromium or an installed Chrome:

```bash
venv/bin/python -m pip install -e './web[browser]'
venv/bin/playwright install chromium
make web-browser-test
```

To use Chrome, pass `BROWSER_FLAGS="--browser-channel chrome"`. On Linux, Playwright's `install --with-deps chromium` can install the required system dependencies. See [web/README.md](../web/README.md) to run the application locally.

The Makefile uses POSIX paths. On Windows, create `venv` with `py -3.11 -m venv venv`, activate it, and install with `python -m pip install -e '.[dev]' -e './web[dev,browser]'`. Invoke Python tools directly; the [CI workflow](workflows/ci.yml) contains the Windows regression and installed-package commands.

## Check changes

Run focused tests during implementation and the relevant complete checks before review: `make ci`, `make web-ci`, `make web-browser-test`, and `make docs-check`. For distribution changes, also run `make build metadata-check distribution-check`. See [MAINTENANCE.md](../MAINTENANCE.md) for release and deployment checks.

Install development hooks with `venv/bin/pre-commit install`. They run lint and formatting, strict type checks, Python tests selected from changed files, and the README tree check. `make pre-commit-check` runs them over all files and may apply formatting fixes. A change affecting shared behavior still needs the relevant complete suite.

Stage source additions, deletions, and moves before running `venv/bin/treestamp update README.md`; inspect and stage the resulting README separately. Treestamp and its hooks never stage or commit files. `make integration-check` verifies the staged tree against the README. After committing a candidate, `make hook-check` verifies hooks installed from that HEAD; it does not cover uncommitted changes.

Preserve exact path identity, frozen editing snapshots, and draft recovery on failed operations. Keep Markdown prose unwrapped. Include release notes when a change requires users to modify their documents or workflows. Automated browser tests do not replace a manual check of keyboard operation, terminal display, or clipboard behavior.
