# Design

Treestamp produces a curated directory tree of a Git repository and maintains it inside a Markdown document. It ships as two released assets:

- the `treestamp` Python package on PyPI, providing the command-line interface, the terminal editor, and the pre-commit hooks
- the hosted web editor at <https://treestamp.reponomics.org>, a FastAPI service in `web/` that uses the same package and is deployed as a container on Fly.io

This document describes system boundaries, data flow, and interface contracts. The [CLI reference](cli-reference.md) describes terminal usage, [UI flow](ui-flow.md) describes browser interactions, and [UI patterns](ui-patterns.md) defines shared web controls. The [security assessment](security-assessment.md) builds on the boundaries described here.

## Actors

| Actor | Description |
| --- | --- |
| Local user | Runs the CLI or terminal editor against a checkout they control |
| Git | The local `git` executable, invoked as a subprocess to read the index and Git objects |
| Local filesystem | Holds the document Treestamp reads and, for `update` and **Write**, replaces |
| Clipboard | A native clipboard command (such as `pbcopy`) or the terminal, through OSC 52, receives copied output |
| Pre-commit and CI | Run `treestamp check` or `treestamp update` without user interaction |
| Web visitor | Uses the hosted editor in a browser |
| Hosted service | The FastAPI application, running on two Fly.io Machines |
| GitHub REST API | Supplies public repository metadata, trees, and blobs to the hosted service |
| Cloudflare and Fly.io | Provide DNS, TLS, and request routing in front of the hosted service |
| Contributor | Opens issues and pull requests; pull-request code runs in CI without secrets |
| Maintainer | Reviews and merges changes; see [GOVERNANCE.md](./GOVERNANCE.md) |
| Dependabot | Opens dependency update pull requests |
| Release Please | A GitHub App that opens release pull requests and, once they are merged, creates tags and GitHub Releases |
| GitHub Actions | Runs CI, scanning, Release Please, PyPI publication, and production deployment |
| PyPI | Distributes the package |

## Core package

The core modules are organized as follows:

| Module | Responsibility |
| --- | --- |
| `cli.py` | Parses arguments and dispatches to extraction, generation, maintenance, or the editor |
| `cli_inputs.py` | Resolves cwd-based source paths and prepares loaded or new sessions |
| `cli_maintenance.py` | Prepares automatic writes and detects notes omitted from their final output |
| `gitio.py` | Runs `git` and captures an immutable snapshot of the index |
| `sources.py` | Builds the same tree from GitHub Trees API records, without a checkout |
| `model.py`, `session.py` | Immutable tree data and the curation state (expanded, hidden, annotated) |
| `codec.py` | Renders and parses tree rows, and checks that parsing the output reproduces the authored tree |
| `maintenance.py` | Updates a printed tree against a newer snapshot, preserving curation at matching paths and entry kinds |
| `document.py` | Finds the marked region, reads its settings, and writes the document atomically |
| `editor.py`, `tui.py`, `tui_dialogs.py` | The Textual terminal editor |

### Local actions

Local source acquisition captures an immutable Git index snapshot. The editor derives curation state from that snapshot and an optional loaded document; subsequent edits do not reread the filesystem tree. Stored paths are repository-relative, while displayed paths are relative to the selected subtree. Document operations stay within the selected repository and reject symlink traversal and submodule-boundary crossings.

Document reads locate one marked region and validate its tree and metadata. Loading into an editor applies automatic maintenance against the snapshot and retains unmatched notes for explicit transfer decisions. Extraction reads the stored region without acquiring a source snapshot. The [CLI reference](cli-reference.md) defines how commands choose these operations and handle unmatched notes.

Writes render a replacement region while preserving surrounding bytes and supported document formatting. Preparation records the destination's content; publication refuses the write if that content has changed. A temporary file in the same directory replaces the destination atomically. The terminal editor writes only to its loaded document. Draft edits remain in memory until exported or written.

Clipboard output uses a native clipboard command from `PATH`, falling back to terminal OSC 52. The core package makes no network requests.

## Hosted editor

The service in `web/src/treestamp_web/` adapts the core package to HTTP:

| Module | Responsibility |
| --- | --- |
| `app.py` | Routes, error mapping, security headers, rate limits, and structured logs |
| `links.py` | Parses user-entered repository links into a validated owner, name, and ref |
| `github.py` | GitHub REST client with response-size caps, timeouts, and a shared request budget |
| `cache.py` | Temporary in-memory snapshot retention (one hour, renewed by successful edits) |
| `preview.py` | Opens and edits a document against one snapshot |
| `limits.py` | Per-client token-bucket rate limits, held in process memory |
| `proxy.py` | Accepts a visitor address from `CF-Connecting-IP` only when the peer is a configured Cloudflare range |
| `routing.py` | Fly.io session affinity, so a session's requests reach the Machine holding its snapshot |
| `static/` | The browser application, served from the same origin |

### Hosted actions

1. The visitor enters a repository link. The service confirms through the GitHub API that the repository is public, resolves its default branch to a commit and tree, and fetches the complete recursive tree listing. Private repositories, branches, and tags are refused; the service opens the current default-branch HEAD or an available cached commit. An uncached pinned commit can be acquired only if it still matches that HEAD.
2. The service fetches the blobs it needs: symlink targets in the selected subtree, up to a configured limit, and the selected document, up to 1 MiB.
3. The service returns the rendered tree, display rows, and a session state envelope to the browser. The browser holds the curation state; the server keeps only the cached snapshot.
4. Each edit sends the state envelope and one operation to the service, which validates both, applies the operation, and returns the new state. Requests for a snapshot that is no longer cached fail with `410` rather than reading a newer commit.
5. The visitor copies the result to the clipboard.

In production, the service authenticates to GitHub as a GitHub App, using the App's private key to obtain installation tokens; [web/README.md](../web/README.md) lists the options for local development. It logs structured events containing the repository name, commit, result, and request budget, not document contents.

The browser's **Resume session** action is an ephemeral convenience for brief return visits, with no recovery guarantee. State-bearing URLs and local records do not constitute durable saved sessions. See [Web UI flow](ui-flow.md#best-effort-return-convenience). Exported document formats are independent of this convenience.

## Build and release

[MAINTENANCE.md](./MAINTENANCE.md) describes CI, releases, PyPI publication, and deployment of the hosted editor.

## External interfaces

The Python modules are not a supported library interface.

### Command line

The CLI exposes source creation, document loading and extraction, read-only comparison, and guarded updates. It selects repository context before invoking the shared engine. The [CLI reference](cli-reference.md) owns command syntax, path defaults, exit status, and terminal editor controls.

### Document format

[ADR 0004: SVG artifacts with an embedded textual treestamp](adr/0004-structured-svg-artifacts.md) proposes paired SVG reading and writing with the complete existing textual treestamp embedded as metadata. Visual styles, container handling, and file destinations are separate from editing and ephemeral session recovery. This is design work for a future release, not an implemented interface.

The [README](../README.md#3-add-it-to-your-readme) shows a complete region and describes its markers, drawing styles, and annotations. A document contains exactly one region.

The optional config comment holds TOML with three keys, each generated only when needed: `root`, the repository-relative subtree the tree displays (default `.`); `hidden`, the repository-relative paths of hidden entries; and `special_paths`, records pairing a printed row number with the full path of an entry whose own name contains reserved annotation or symlink syntax, or ends in the Git-link marker. Equivalent authored configuration may include explicit defaults. Other keys are rejected. Annotations follow a fixed `  # ` delimiter.

New regions have one blank line after the start marker, between configuration and tree, and before the end marker. Existing regions retain zero or one blank line independently at each applicable boundary. Configuration text is retained while its validated TOML values are unchanged, regardless of wrapping, comments, or quoting. Changed configuration is regenerated, dropping its comments, with short arrays inline and longer arrays compactly wrapped at an 80-character target. Individual entries are never split; the target is not a validation limit.

`prepare_content` applies these preservation rules before the complete byte comparison used by `check` and editor dirty-state detection. It does not ignore arbitrary tree whitespace or bypass schema and identity validation. Loaded exports and existing-file writes preserve the document's LF or CRLF convention; new documents use LF. Both editors use the same preparation path for loaded exports; the terminal editor writes back only to the loaded document. Session state carries no separate formatting preference. [ADR 0002](adr/0002-formatter-compatible-documents.md) records the formatting rationale and alternatives.

The optional attribution footer is disabled by default. When present, the exact line `Maintained with [treestamp](https://github.com/reponomics/treestamp)` follows the closing code fence or Markdown list, separated by a blank line, before the end marker. The parser infers the attribution setting from this line, so it survives loading and maintenance without an additional config key. Session state carries the boolean `attribution` setting; older states that omit it default to false.

[Resolve special filenames by row](special-path-resolution.md) specifies the `special_paths` record format, how rows are numbered, and how registrations are validated. Manual tree edits are supported only for annotation text; treestamp owns filenames, structure, and metadata values. Equivalent TOML formatting and the supported boundary spacing may be changed by users or formatters without changing those values.

### Pre-commit hooks

`.pre-commit-hooks.yaml` defines `treestamp` (runs `treestamp update`) and `treestamp-check` (runs `treestamp check`). Both run on every commit and receive no filenames.

### Hosted HTTP API

The browser application uses these endpoints. They exist to serve that application and are not a supported public API.

| Endpoint | Input | Output |
| --- | --- | --- |
| `GET /` | None | The browser application |
| `GET /{owner}/{repo}` | A repository owner and name in the path | The browser application, which then opens that repository |
| `GET /api/browse` | Repository `url` | Source entries for selecting a root folder or document |
| `GET /api/preview` | Query parameters `url`, or `owner` and `repo`; optional `ref` (a commit id), `root`, `document` | A preview: repository, resolved commit and tree, settings, rendered tree and region, display rows, warnings, permalink, and state envelope |
| `POST /api/preview` | The same fields as a JSON object | The same as `GET` |
| `POST /api/op` | JSON with `owner`, `repo`, `ref` (a 40-character commit id), `root`, `document`, `state` (the envelope), `op` (`type` plus `path` or `text`), and `reveal` | An updated preview |
| `POST /api/placement` | Captured source and opening `state`, bounded `decisions`, browsing `expanded` paths, and `reveal` | Provisional placement state and destination rows |
| `GET /healthz` | None | Liveness, versions, build commit, credential type, last observed GitHub budget, and cache statistics |

The state envelope carries the curation (expanded and hidden paths, annotations, and settings), the source it was created from, the original marked treestamp-region bytes, an optional `initial_curation` baseline, and a revision counter. The browser sends the latest envelope with current presentation settings and the requested operation. Operation types:

| Type | Effect |
| --- | --- |
| `toggle`, `expand`, `collapse` | Change whether the directory at `path` is expanded |
| `hide`, `unhide` | Hide or show the entry at `path` |
| `unhide_all` | Show all hidden entries |
| `annotate` | Set the annotation of `path` to `text`; empty text removes it |
| `present` | Re-render with the settings in the state, such as drawing style or counts |
| `restore` | Re-render a captured session without counting as an edit |
| `reset` | Restore `initial_curation`, captured after note placement, against the same snapshot |

`reveal` controls whether display rows include hidden entries; it does not change the printed tree. Request bodies are limited to 256 KiB. Errors return a JSON object with a stable `code` and a message, using `400`, `404`, `409`, `410`, `413`, `422`, `429` (with `Retry-After`), `503`, or `504`.
