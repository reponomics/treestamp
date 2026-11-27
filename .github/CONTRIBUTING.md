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

Use Python 3.11+ and the uv version pinned by the `ghcr.io/astral-sh/uv` image in `web/Dockerfile` (`make uv-check` reports a mismatch) to manage a virtual environment named `venv`. Install uv through its official standalone installer or your system package manager; do not bootstrap it through an outdated pip. JavaScript checks use the Node version in `.nvmrc`, selected through nvm. The frontend has no npm installation or bundling step.

```bash
make venv
make install
nvm install
nvm use
```

`make install` synchronizes both packages, build tools, and all test dependencies from the committed `uv.lock`. It fails if the dependency declarations have changed without updating the lock. `make web-install` and `make web-browser-install` are aliases for the same workspace setup. See [browser installation](#browser-tests) and [workflow linting](#workflow-linting) below for additional tools, and [web/README.md](../web/README.md) to run the application locally.

The Makefile uses POSIX paths. On Windows, set `UV_PROJECT_ENVIRONMENT=venv`, then run `uv sync --locked --all-packages --all-extras --no-install-workspace --no-build` followed by `uv sync --locked --all-packages --all-extras --no-build-isolation`. Activate `venv` and invoke Python tools directly; the [CI workflow](workflows/ci.yml) contains the Windows regression and installed-package commands.

## Dependencies

Prefer the standard library and existing dependencies. Propose a new dependency in the pull request that adds it, explaining why it is needed. It must be actively maintained, publish wheels for the supported Python versions and platforms, and have a license in the allowlist of the [dependency scan](workflows/osv-scanner.yml), which checks every locked package. Any other license, including copyleft licenses, needs the maintainer's review and a recorded exception in `osv-scanner.toml`. A dependency found to violate this is replaced or removed before the next release. Declare the core package's runtime dependencies in `pyproject.toml`, the hosted editor's in `web/pyproject.toml`, and development tools in the `dev` extras.

Dependencies are obtained from PyPI through uv. For intentional dependency changes, edit the appropriate `pyproject.toml`, run `uv lock`, and commit the lock with the declarations. Use `make lock-update` for a deliberate full dependency refresh, or `uv lock --upgrade-package NAME` for a targeted update. Re-run `make install` and the relevant checks. The lock manages repository development and deployment; the published package retains compatible dependency ranges.

[Dependabot](dependabot.yml) proposes updates and OSV-Scanner checks the locked dependencies for known vulnerabilities. [MAINTENANCE.md](../docs/MAINTENANCE.md#dependencies-and-toolchain) covers reviewing these updates and the pinned toolchain versions.

## Tests for changes

Follow the [testing policy](../docs/testing.md) for regression coverage, suite responsibilities, measurement boundaries, and verification limits.

## Check changes

Run commands from the repository root after setup. Install the staged-file Git hook with `venv/bin/pre-commit install`.

| Checkpoint | Command | Scope |
| --- | --- | --- |
| Before committing | `make check:pre-commit` | Development hooks on staged files: formatting/lint, applicable types, selected Python tests, and README freshness |
| Before opening or updating a PR | `make check:pr` | Toolchain and lock checks, workflow lint, core/hosted/JavaScript/browser suites, documentation and README checks, package and installed-hook acceptance, and the container build |

The staged hook may apply formatting changes; inspect and restage them before retrying. `make pre-commit-check` runs the development hooks over all files. Selected tests do not replace complete suite verification for shared behavior changes.

Python test and coverage targets, including staged-file tests, treat implicit text-encoding warnings as errors in both the test runner and its Python subprocesses. Specify the intended encoding when reading or writing text, including in fixtures.

The PR checkpoint requires [Chromium](#browser-tests), [actionlint](#workflow-linting), a running Docker daemon, and network access for package installation and container images. Commit the candidate before the final run because installed-hook acceptance reads `HEAD`. Run one checkpoint per invocation so formatting and environment changes do not race with tests.

Stage source additions, deletions, and moves before running `venv/bin/treestamp update README.md`; inspect and stage the resulting README separately. If unmatched notes block the update, follow the [README maintenance instructions](../docs/MAINTENANCE.md#readme-tree-and-alternate-styles). Treestamp and its hooks do not stage or commit files. `make integration-check` verifies the staged tree against the README.

Preserve exact path identity, frozen editing snapshots, and draft recovery on failed operations. Keep Markdown prose unwrapped. Include release notes when a change requires users to modify their documents or workflows. Update affected documentation in the same pull request.

### Focused checks

| Command | Scope |
| --- | --- |
| `make test` | Core Python regression suite |
| `make web-test` | Hosted Python suite |
| `make web-browser-test` | Browser journeys |
| `make web-js-test` | Pure JavaScript logic; also `npm --prefix web test` |
| `make ci` | Core lint, formatting, types, and coverage gate |
| `make web-ci` | Hosted lint, formatting, types, Python coverage, and JavaScript logic coverage |
| `make docs-check` | Local document destinations and packaged README URLs; excludes remote availability and fragment anchors |
| `make integration-check` | README treestamp and generated style previews |

For a disposable terminal note-transfer fixture, run `make reconcile-demo`. It creates a temporary repository with moved and removed paths and launches the editor there.

### Browser tests

Install a browser after the Python dependencies:

```bash
venv/bin/playwright install chromium
make web-browser-test
```

Use `BROWSER_FLAGS="--browser-channel chrome"` for installed Chrome. On Linux, `venv/bin/playwright install --with-deps chromium` also installs system dependencies. Browser tests run separately from the hosted suite because Playwright's event loop conflicts with its use of `asyncio.run`.

For optional visual inspection, follow the [UI review protocol](../docs/ui-review.md).

### Workflow linting

Install GitHub CLI and authenticate with `gh auth login`, or provide `GH_TOKEN`. Then install and run the version pinned in `.tool-versions`:

```bash
make actionlint-install
make workflow-check
```

The installer verifies the release's GitHub artifact attestation before extracting or executing it. It supports macOS and Linux on x86_64 and ARM64 and installs into `.tools/bin/`. `ACTIONLINT=/path/to/actionlint` overrides the destination and executable; `GH=/path/to/gh` overrides GitHub CLI. Missing or mismatched versions fail with installation guidance. Tool upgrades are covered in [Maintenance](../docs/MAINTENANCE.md#dependencies-and-toolchain).

### Coverage reports

| Command | Report |
| --- | --- |
| `make cov` | Core Python statements and branches |
| `make web-cov` | Hosted Python statements and branches |
| `make web-js-cov` | JavaScript logic lines, branches, and functions |
| `make cov-python` | Both Python suites, followed by their combined report |
| `make cov-all` | Combined Python coverage and a separate JavaScript report |

`cov-python` runs the suites sequentially with their independent gates, then combines `.coverage` and `web/.coverage` into `.coverage.python`. It removes an old aggregate before running and stops if either suite fails. `make clean` removes these files.

Pass `COV_ARGS` to produce additional Python report formats:

```bash
make cov COV_ARGS=--cov-report=json:/tmp/treestamp-core.json
make web-cov COV_ARGS=--cov-report=xml
```

XML reports are written as `coverage.xml` and `web/coverage.xml`. The [coverage workflow](workflows/coverage.yml) uploads these to Codecov with separate core/web flags and the path correction in [codecov.yml](../codecov.yml). JavaScript coverage is also available through `npm --prefix web run test:coverage`. See the [testing policy](../docs/testing.md#measurement-scope) for report boundaries.
