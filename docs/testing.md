# Testing policy

This document defines test expectations, suite responsibilities, and coverage measurement. [Contributing](../.github/CONTRIBUTING.md#check-changes) describes how to run the checks; [Maintenance](MAINTENANCE.md) describes release validation and CI configuration.

## Changes and regression coverage

Non-trivial behavior changes require automated tests in the same pull request. Tests should assert observable outcomes, including failure recovery. High-impact changes need coverage of relevant failure cases and boundaries, such as path identity, document preservation, snapshot consistency, and rejected operations that must leave a draft intact.

Changes that leave behavior unchanged, such as documentation edits or refactoring covered by existing tests, need no new tests. Dependency updates require the relevant regression suites; add tests when the update exposes a missing behavioral check.

Prefer deterministic fixtures and controlled clocks or transports. Avoid assertions on incidental wording, elaborate mocks for unreachable states, and tests that only mirror the implementation. Integration tests should exercise public interfaces and real component boundaries where practical.

Focused tests provide feedback during development. Relevant complete suites are required before review. Automated browser and headless terminal tests do not establish that real terminals, native clipboards, or responsive layouts work correctly in every environment.

## Suite responsibilities

| Suite | Responsibility |
| --- | --- |
| Core Python | CLI behavior, document parsing and transactional writes, Git snapshots, tree maintenance, and headless terminal editor journeys |
| Hosted Python | HTTP contracts, GitHub acquisition, snapshot and state validation, caching, request budgets, and resource limits |
| Browser | End-to-end browser interactions against a local service and fake GitHub API, including recovery from rejected requests |
| JavaScript logic | Pure browser-side logic without DOM or network dependencies |
| Installed-package acceptance | Wheel and source-distribution contents, clean installations, CLI commands, terminal editor workflows, and installed repository hooks |

Hosted tests use controlled GitHub responses or local repository fixtures. Bundled examples are checked against the API representation. Tests must not rely on mutable public repository contents for repeatable results.

The CI matrix checks supported Python versions on Linux and Windows. Local validation covers the machine and environment on which it runs. Container build and health checks, dependency scanning, and static analysis complement the behavioral suites; they do not replace them. The [CI workflow](../.github/workflows/ci.yml) defines the execution matrix.

## Coverage policy

Core and hosted Python suites each enforce a **95% minimum**, measured independently. PRs should avoid reducing coverage by more than one percentage point; this review guideline is separate from the enforced minimum. JavaScript logic coverage is reported without a percentage gate. Codecov statuses are informational; the local and CI quality gates enforce the Python minimums.

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

The [optional UI review protocol](ui-review.md) describes a bounded visual inspection process. Successful screenshot capture alone is not evidence that the captured views were inspected.
