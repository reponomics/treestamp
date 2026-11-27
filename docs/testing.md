# Testing policy

This document defines test expectations, suite responsibilities, and coverage measurement. [Contributing](../.github/CONTRIBUTING.md#check-changes) describes how to run the checks; [Maintenance](MAINTENANCE.md) describes release validation and CI configuration.

## Changes and regression coverage

Non-trivial behavior changes require automated tests in the same pull request. Tests should assert observable outcomes, including failure recovery. High-impact changes need coverage of relevant failure cases and boundaries, such as path identity, document preservation, snapshot consistency, and rejected operations that must leave a draft intact.

Changes that leave behavior unchanged, such as documentation edits or refactoring covered by existing tests, need no new tests. Dependency updates require the relevant regression suites; add tests when the update exposes a missing behavioral check.

Prefer deterministic fixtures and controlled clocks or transports. Avoid assertions on incidental wording, elaborate mocks for unreachable states, and tests that only mirror the implementation. Integration tests should exercise public interfaces and real component boundaries where practical.

Tests verify current requirements in the [design reference](design.md) and user documentation, together with explicitly identified implementation assumptions. A failure identifies a discrepancy; it does not establish which behavior the product should retain. When intended behavior changes, update the relevant documentation, generators, expectations, and regression cases together. Cache-specific tests describe the current mechanism; they do not establish retention, persistence, or session-sharing guarantees.

Text I/O must specify its encoding; Python validation treats `EncodingWarning` as an error. Fixtures for byte-sensitive document behavior must control line endings explicitly. Git-index fixtures must use paths valid on supported platforms; unusual path encodings can be exercised through Git objects without checking those paths out.

Focused tests provide feedback during development. Relevant complete suites are required before review. Automated browser and headless terminal tests do not establish that real terminals, native clipboards, or responsive layouts work correctly in every environment.

## Suite responsibilities

| Suite | Responsibility |
| --- | --- |
| Core Python | CLI behavior, document parsing and transactional writes, Git snapshots, tree maintenance, and headless terminal editor journeys |
| Hosted Python | HTTP behavior, GitHub acquisition, snapshot and state validation, caching, request budgets, and resource limits; generated request-parser checks |
| Browser | End-to-end browser interactions against a local service and fake GitHub API, including recovery from rejected requests and focused regressions |
| JavaScript logic | Pure browser-side logic without DOM or network dependencies |
| Installed-package acceptance | Wheel and source-distribution contents, clean installations, CLI commands, terminal editor workflows, and installed repository hooks |

Hosted tests use controlled GitHub responses or local repository fixtures. Bundled examples are checked against the API representation. Tests must not rely on mutable public repository contents for repeatable results.

The CI matrix checks supported Python versions on Linux and Windows. Local validation covers the machine and environment on which it runs. Container build and health checks, dependency scanning, and static analysis complement the behavioral suites; they do not replace them. The [CI workflow](../.github/workflows/ci.yml) defines the execution matrix.

## Generated tests

Generated (property-based) tests use [Hypothesis](https://hypothesis.readthedocs.io/) within the core and hosted suites. The initial scope is document serialization and parsing, core session transport, and hosted request parsing. Tests and shared strategies live in `tests/properties/` and `web/tests/properties/`, and run in the ordinary test and coverage suites. Core session transport checks fidelity within the current implementation, not persisted sessions or cross-version compatibility. Browser logic uses ordinary JavaScript tests and focused browser regressions; the Python suites do not require Node.

Expected results come from the generated model or from an independent oracle, not from the transformation under test. The representability predicate describes limitations of the current printed format, not a prohibition on supporting more inputs. It checks rejection for those cases and faithful round trips otherwise. When the format changes, update this predicate and its examples along with the implementation. Narrowing generators merely to hide unexpected failures is not a substitute for deciding the intended behavior.

Each property directory's `conftest.py` registers two profiles derived from Hypothesis's default: `ordinary` (100 examples per property, used by ordinary runs) and `extended` (1,000 examples). Both disable per-example deadlines and use a fresh random seed; the explicit profile overrides the derandomized profile Hypothesis selects automatically under CI. `make test-properties` runs only the property suites, and `make test-properties-extended` runs them with the extended budget.

The [Extended Hypothesis tests workflow](../.github/workflows/properties.yml) runs the extended suites daily at 07:23 UTC on the default branch and is available through **Actions → Extended Hypothesis tests → Run workflow**, selecting the desired branch. GitHub may delay scheduled runs. Ordinary properties remain part of normal PR checks. Daily runs explore additional generated combinations without requiring periodic runs on a maintainer's machine.

The extended job uses read-only repository permissions, no production credentials, and a ten-minute timeout. Dependency installation accesses package sources; the property tests operate on synthetic inputs inside the runner and do not contact the deployed editor, GitHub APIs, or external test repositories. No Hypothesis database is retained between workflow runs.

A failing property makes pytest, the Make target, and the workflow fail. Hypothesis attempts to simplify generated counterexamples and prints the failing input, assertion or traceback, and a `@reproduce_failure` decorator in the test log. Setup failures, health-check failures, and interrupted or timed-out runs may not produce a replayable example. The maintainer or contributor investigating a failed run uses the logged reproduction information with the tested revision and locked dependencies. The decorator is a temporary debugging aid tied to the Hypothesis version; confirmed defects should receive an explicit example or focused regression for the intended behavior. A minimized counterexample alone does not decide product policy.

Failure logs are publicly visible for this public repository. The workflow does not classify severity, open issues or advisories, or privately route security-sensitive examples. A generated failure can reveal a vulnerability before it is assessed. Investigate suspected vulnerabilities through the [security reporting process](../.github/SECURITY.md); that process does not make already-published CI output private.

Hypothesis also replays recent failures from its local `.hypothesis/` database, which is not committed and which CI does not rely on.

## Coverage policy

Core and hosted Python suites each enforce a **95% minimum**, measured independently, through local and CI checks. For PRs targeting `main`, a repository ruleset also enforces a **95% minimum coverage and a maximum decrease of one percentage point** on reported coverage results. These thresholds are configured directly in the ruleset; the maximum decrease is an enforced requirement, not only a review guideline. Codecov's own project and patch status checks remain informational, separately from ruleset enforcement. JavaScript logic coverage is reported without a percentage gate.

Python percentages combine executable statements and branch destinations. The combined Python report uses total covered and total measured items across both suites, rather than averaging their percentages. Core execution during hosted tests does not add coverage to the independently measured core report.

JavaScript reports lines, branches, and functions. Its percentages are kept separate from Python because the measurement units differ. A combined whole-application percentage is not reported.

### Measurement scope

| Report | Included | Outside its denominator |
| --- | --- | --- |
| Core Python | `src/treestamp/` | Maintenance/deployment scripts and test harnesses |
| Hosted Python | `web/src/treestamp_web/` | Core package, scripts, and test harnesses, including browser tests |
| JavaScript | `web/src/treestamp_web/static/logic.js` | DOM code, theme code, generated examples, and browser interactions |

Child processes are not instrumented. CLI subprocess tests, installed-package checks, and the browser fixture's Uvicorn process therefore do not contribute execution hits. Package source remains in its denominator even when exercised only in a child process, so an uncovered line is not necessarily untested.

Coverage measures execution, not assertion quality or correctness. Excluded components may still have tests, and complete pure-logic coverage does not establish complete frontend coverage. Coverage reports must state their scope; removing difficult code from the denominator is not a substitute for testing it.

## Verification limits

| Area | Evidence needed beyond coverage |
| --- | --- |
| Native clipboard and OSC 52 | Actual delivery in supported operating-system and terminal environments |
| Terminal rendering and focus | Interaction in real terminal emulators; headless Textual tests cannot establish physical display behavior |
| Browser layout | Inspection at relevant viewport sizes, alongside functional browser tests |
| Filesystem failures and concurrent writes | Deterministic failure tests and prepared-write interleavings, with platform-specific checks where needed |
| Defensive validation | Reachable boundary failures; synthetic internal corruption should be identified as such |
| Generated tests | Small bounded inputs; these do not establish resistance to resource exhaustion or replace a security review |

The [optional UI review protocol](ui-review.md) describes a bounded visual inspection process. Successful screenshot capture alone is not evidence that the captured views were inspected.
