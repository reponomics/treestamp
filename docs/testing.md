# Testing

This is the canonical guide to Treestamp's testing policy, commands, coverage reporting, and recorded verification status. For environment setup, see [Contributing](../.github/CONTRIBUTING.md#set-up); for release and deployment procedures, see [Maintenance](MAINTENANCE.md).

## Which command should I run?

Use two checkpoints. The existing granular targets remain available for focused work.

| Checkpoint | When | What it runs |
| --- | --- | --- |
| `make check:pre-commit` | After staging changes, before committing | Configured development hooks against staged files: formatting/lint, applicable type checks, selected Python tests, and README freshness |
| `make check:pr` | Before opening or updating a PR | Toolchain/lock checks, workflow lint, a fresh package build, core/hosted/JavaScript/browser quality gates, documentation and README checks, package metadata and clean-install acceptance, committed-hook acceptance, and the hosted container build |

`check:pre-commit` uses the same staged-file behavior as the installed Git hook. It may modify formatting and fail until you inspect and restage those changes. Use `make pre-commit-check` only when you intentionally want the development hooks to inspect all files. Neither hook entry point substitutes for the PR checkpoint.

After [environment setup](../.github/CONTRIBUTING.md#set-up) and [browser installation](#suites-and-commands), the PR checkpoint also requires actionlint on `PATH`, a running Docker daemon, and network access for package installation and container base images. Commit the candidate before the final PR run: most checks exercise the working tree, but installed-hook acceptance reads committed `HEAD`.

```bash
make check:pre-commit
# Inspect and commit the candidate, then:
make check:pr
```

The PR checkpoint completes environment synchronization and package building before launching tests or artifact checks, including when invoked with `make -j`. It builds into a fresh temporary directory, removes that directory on completion or failure, and leaves existing `dist/` artifacts untouched. The granular `build`, `metadata-check`, and `distribution-check` targets still default to `dist/`, or accept `DIST_DIR=...` when used independently. A failed phase makes the checkpoint fail; no checks are silently skipped because a tool is missing. Run one checkpoint per invocation, since formatting hooks can modify the files being tested.

A green PR checkpoint verifies the existing local checks on the current machine and Python version. GitHub CI still supplies these additional responsibilities:

| CI responsibility | Where |
| --- | --- |
| Linux/Windows and supported Python version matrix | [CI workflow](../.github/workflows/ci.yml) |
| Starting the built container and probing `/healthz` | Hosted job in the [CI workflow](../.github/workflows/ci.yml); the local checkpoint builds the image |
| Dependency/license analysis, Scorecard, and CodeQL | [OSV workflow](../.github/workflows/osv-scanner.yml), [Scorecard workflow](../.github/workflows/scorecard.yml), and GitHub's configured CodeQL analysis |
| Coverage upload | [Coverage workflow](../.github/workflows/coverage.yml); [Codecov statuses are informational](#coverage-reporting) |

See [repository setup](MAINTENANCE.md#repository-and-release-setup) for merge requirements. These checkpoints validate a candidate; they do not publish packages or deploy the service.

## Policy

Both Python suites must meet **95% coverage**, measured separately for the core package and hosted editor. The [Makefile](../Makefile) enforces this minimum through `make cov` and `make web-cov`, also run by `make ci` and `make web-ci`. PRs should avoid reducing coverage by more than 1%, if at all; that regression guideline is separate from the enforced minimum. JavaScript coverage is reported without a percentage gate.

Non-trivial changes must add or update automated tests in the same pull request, and high-impact changes need thorough testing. Assert observable behavior, including failure recovery, rather than merely executing lines. Prefer deterministic fixtures, boundary cases, and tests that preserve exact path identity, frozen snapshots, and drafts after failed operations. Avoid brittle assertions on incidental strings, elaborate mocks for unreachable states, and redundant tests that add little assurance.

Changes that leave behavior unchanged, such as documentation, refactoring already covered by existing tests, and dependency updates that pass the relevant suites, need no new tests. Run focused checks while implementing a change and the relevant complete checks before review. Automated browser tests do not replace manual checks of keyboard operation, terminal display, or clipboard delivery.

## Suites and commands

Run commands from the repository root after `make install`; use the Node version in `.nvmrc` through nvm. The frontend needs no npm installation or bundling step.

| Suite or check | Command | Scope |
| --- | --- | --- |
| Core quality gate | `make ci` | Formatting, lint, strict Python types, and core tests with the coverage gate |
| Hosted quality gate | `make web-ci` | Web formatting, lint, strict types, hosted Python coverage gate, and JavaScript logic coverage |
| Core tests only | `make test` | CLI, document parsing/writing, Git snapshots, tree maintenance, and headless terminal editor journeys in `tests/` |
| Hosted tests only | `make web-test` | API, GitHub client, snapshots, cache, and limits in `web/tests/` |
| Browser journeys | `make web-browser-test` | `web/tests/browser/` against a local service and fake GitHub API |
| JavaScript logic | `make web-js-test` | Pure logic tests in `web/tests/js/`; also `npm --prefix web test` |
| Documentation | `make docs-check` | Local destinations and canonical packaged README URLs; does not validate remote availability or fragment anchors |
| Repository tree | `make integration-check` | README's managed tree and alternate style previews |

Hosted tests use a fake GitHub API backed by a local fixture repository; cache and quota tests use controlled clocks and transports. Browser tests run in their own process because Playwright's event loop conflicts with the other tests' use of `asyncio.run`. Bundled welcome examples are offline fixtures; `web/tests/test_examples.py` checks that `web/src/treestamp_web/static/example.js` and `web/src/treestamp_web/data/examples.json` agree with the API.

Browser dependencies are included by `make install`, but a browser must be available separately:

```bash
venv/bin/playwright install chromium
make web-browser-test
```

Use `BROWSER_FLAGS="--browser-channel chrome"` for an installed Chrome. On Linux, `venv/bin/playwright install --with-deps chromium` also installs the required system dependencies. The Makefile uses POSIX paths; see the [Windows setup instructions](../.github/CONTRIBUTING.md#set-up) for direct Python invocations.

Package acceptance and the hosted container build are included in `make check:pr`. The [maintenance runbook](MAINTENANCE.md#validate-and-build) explains the underlying build and installed-package checks for focused use. Keep deployment smoke checks in the [production deployment procedure](MAINTENANCE.md#production-deployment).

## CI and local hooks

The local `check:pr` target and the primary Linux CI jobs share two internal Make phases. `_check-pr-core` owns toolchain/lock/workflow checks, environment synchronization, a fresh temporary build, core quality gates, documentation/README checks, and package/hook acceptance. `_check-pr-web` owns hosted Python/JavaScript quality gates, browser journeys, and the container build. Add or remove checks in these Make phases rather than maintaining another list in workflow YAML. The local checkpoint finishes the core phase before starting the hosted phase so dependency synchronization cannot race with tests; CI runs them in isolated jobs. CI installs actionlint 1.7.12 from a checksum-verified release archive before the core phase.

The Python 3.12 compatibility job, Windows matrix, coverage uploads, README-only workflow, and release publication retain their narrower commands and artifact lifecycles. The staged-file `check:pre-commit` target is intentionally local: a clean CI checkout has no staged changes to inspect. Release publication keeps its validated artifacts for upload, whereas the PR checkpoint removes its temporary artifacts.

The [CI workflow](../.github/workflows/ci.yml) runs on pull requests to `main` and pushes to `main`. Core regression tests run on Linux and Windows with Python 3.11 and 3.12; clean installed-package checks run on Linux 3.11 and both Windows versions. Linux with Python 3.11 also runs the complete quality gates and distribution metadata checks; the hosted job runs web quality gates, Chromium journeys, and a container health probe. CI logs contain test summaries, missed coverage lines, or README diffs when checks fail. The [maintenance runbook](MAINTENANCE.md#repository-and-release-setup) describes required checks and release configuration.

Install local development hooks with `venv/bin/pre-commit install`. They run lint and formatting, strict types, Python tests selected from changed files, and the README tree check. `make pre-commit-check` runs them over all files and may apply formatting fixes. Selected tests are a fast feedback mechanism; shared behavior changes still require the relevant complete suites.

## Coverage reporting

Python totals combine executable statements and branch destinations; they are not line-only percentages. Reports show two decimal places so small remaining gaps stay visible. Run `make cov web-cov web-js-cov` to obtain all three reports, or use individual targets:

```bash
make cov COV_ARGS=--cov-report=json:/tmp/treestamp-core.json
make web-cov COV_ARGS=--cov-report=json:/tmp/treestamp-web.json
make web-js-cov
```

`COV_ARGS=--cov-report=xml` produces `coverage.xml` or `web/coverage.xml`, matching the [coverage workflow](../.github/workflows/coverage.yml). That workflow uploads only Python reports to Codecov using separate core/web flags and the web path correction in [codecov.yml](../codecov.yml). Codecov statuses are informational; the Make targets enforce the coverage minimum. JavaScript reporting is also available through `npm --prefix web run test:coverage` and runs as part of `make web-ci`.

| Report | Included | Outside its denominator |
| --- | --- | --- |
| Core Python | `src/treestamp/` | Maintenance/deployment scripts and test harnesses |
| Hosted Python | `web/src/treestamp_web/` | Core package, scripts, and test harnesses, including browser tests |
| JavaScript | `web/src/treestamp_web/static/logic.js` | `app.js`, `theme.js`, generated examples, and browser interactions |

Child processes are not instrumented: CLI subprocess tests, installed-package checks, and the browser fixture's Uvicorn process do not contribute execution hits to these reports. Package source remains in its denominator even when exercised only in a child process, so an uncovered line is not necessarily untested.

Some excluded components have regression tests; absence from a report does not imply absence of tests. Conversely, 100% pure-logic coverage does not establish 100% frontend coverage. Keep these scopes and limitations explicit when comparing results, and do not remove difficult code from the denominator just to improve a percentage.

## Recorded verification status

Snapshot: **November 12, 2026**, on macOS with Python 3.11.11 and Node 24.22.1. `make -j4 check:pr` passed on candidate `b4f6101`, including both 95% coverage gates and the browser suite. These are local results, not a live CI status or evidence of a fresh Windows/Linux matrix run. `check:pre-commit` also passed against the staged checkpoint definitions.

| Suite | Latest result | Coverage | Remaining measured gaps |
| --- | --- | --- | --- |
| Core Python | 1,003 passed, 1 filesystem-dependent skip | 99.70% statements and branches | 3 statements, 5 branch destinations |
| Hosted Python | 293 passed; browser cases run separately | 99.28% statements and branches | 10 statements, 3 branch destinations |
| JavaScript logic | 23 passed | 100% lines, branches, and functions | None in `logic.js` |
| Chromium browser | 162 passed, 1 known warning | Not collected | See coverage scope above |

The PR checkpoint also passed formatting, lint, strict typing, lockfile/toolchain consistency, workflow lint, documentation and README checks, wheel/sdist metadata and clean-install acceptance, installed-hook acceptance, and the Docker image build. Its first run exposed a copied-interpreter library lookup failure with uv-managed Python; acceptance environments now use symlinks on POSIX and retain copying on Windows. The earlier coverage review raised the core total from 95.97% and the hosted total from 98.11%, adding 58 core cases, 14 hosted cases, and 6 JavaScript tests. Refresh this dated snapshot when recording a new coverage audit or a material testing/dependency change; use CI results for the status of other revisions.

### Test dependencies and known warnings

Starlette's `TestClient` now uses the web development dependency `httpx2>=2,<3`, locked at 2.16.0. The production GitHub client still uses `httpx` 0.28.1, and the tests exercise that same implementation. The former Starlette fallback deprecation warning is resolved: hosted and browser suites passed with `-W error::starlette.exceptions.StarletteDeprecationWarning`. No warning suppression was added.

One browser warning remains: pytest 9.2 reports `PytestRemovedIn10Warning` for the session-scoped `base_url` fixture in pytest-playwright 0.10.0's `_BaseUrlFallback`. This upstream fixture does not use instance state, so the warning does not identify a behavioral failure in these tests. Leave it visible and revisit it when upgrading pytest-playwright; do not add a plugin or local fixture override solely to silence it. The installed plugin constrains pytest to `<10`, preventing a compatible dependency update from crossing the announced removal boundary. Recheck the fixture before accepting a plugin version that permits pytest 10.

## Remaining gaps and cost

Core gaps include the non-entry import branch in `__main__.py`, containment/name consistency guards in `gitio.py` and `model.py`, and empty-count/rejected-browse branches in `tui.py`. Hosted gaps include missing package metadata, defensive exception handlers in `app.py`, and normalization/rendering guards in `preview.py`. Some are inexpensive but low-value checks; others sit behind earlier validation. Not every remaining gap requires a complex harness.

| Area | Useful next assurance | Complexity or limitation |
| --- | --- | --- |
| Native clipboard and terminal OSC 52 | Verify actual delivery on macOS, Windows, Wayland, and X11 | High: OS/session integration; command-selection tests cannot prove delivery. |
| Terminal rendering and focus | Exercise real PTYs and supported terminal emulators | High: headless Textual tests cannot establish physical terminal behavior. |
| Full browser coverage | Instrument browser JavaScript and merge per-page results; instrument the service process separately | Medium/high: lifecycle, subprocess, and source-mapping work; keep these metrics distinct from pure logic. |
| Defensive validation and render/reparse guards | Test realistic boundary failures when reachable | Often low yield: earlier validation can make a guard unreachable through valid public operations; corrupting internal objects or replacing several internals tests a synthetic situation. |
| Filesystem failures and concurrent writes | Keep deterministic permission-failure stubs and prepared-write interleavings | Real OS permissions and timing-based races add platform dependence and flakiness. |
| Package metadata fallbacks | Exercise source-only imports without installed metadata | Low implementation cost, but lower assurance value than draft recovery or parsing checks. |
