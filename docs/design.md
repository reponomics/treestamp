# Design

Treestamp produces a curated directory tree of a Git repository and maintains it inside a Markdown document. It ships as two released assets:

- the `treestamp` Python package on PyPI, providing the command-line interface, the terminal editor, and the pre-commit hooks
- the hosted web editor at <https://treestamp.reponomics.org>, a FastAPI service in `web/` that uses the same package and is deployed as a container on Fly.io

This document describes the actors, the actions each performs, and the external interfaces of both assets. Update it when a change adds or removes an interface, an actor, or a stored or transmitted kind of data. The [security assessment](security-assessment.md) builds on this description.

## Actors

| Actor | Description |
| --- | --- |
| Local user | Runs the CLI or terminal editor against a checkout they control |
| Git | The local `git` executable, invoked as a subprocess to read the index, trees, and history |
| Local filesystem | Holds the document Treestamp reads and, for `update` and **Write**, replaces |
| Clipboard | A native clipboard command (such as `pbcopy`) or the terminal, through OSC 52, receives copied output |
| Pre-commit and CI | Run `treestamp check` or `treestamp update` without user interaction |
| Web visitor | Uses the hosted editor in a browser |
| Hosted service | The FastAPI application, running on two Fly.io Machines |
| GitHub REST API | Supplies public repository metadata, trees, and blobs to the hosted service |
| Cloudflare and Fly.io | Provide DNS, TLS, and request routing in front of the hosted service |
| Contributor | Opens issues and pull requests; pull-request code runs in CI without secrets |
| Maintainer | Reviews and merges changes; see [GOVERNANCE.md](../GOVERNANCE.md) |
| Dependabot | Opens dependency update pull requests |
| Release Please | A GitHub App that opens release pull requests and, once they are merged, creates tags and GitHub Releases |
| GitHub Actions | Runs CI, scanning, Release Please, PyPI publication, and production deployment |
| PyPI | Distributes the package |

## Core package

The modules in `src/treestamp/` have narrow responsibilities:

| Module | Responsibility |
| --- | --- |
| `cli.py` | Parses arguments and dispatches to headless maintenance or the editor |
| `gitio.py` | Runs `git` and captures an immutable snapshot of the index or a ref |
| `sources.py` | Builds the same tree from GitHub Trees API records, without a checkout |
| `model.py`, `session.py` | Immutable tree data and the curation state (expanded, hidden, annotated) |
| `codec.py` | Renders and parses tree rows, and checks that parsing the output reproduces the authored tree |
| `maintenance.py` | Updates a printed tree against a newer snapshot, preserving curation and applying detected moves |
| `document.py` | Finds the marked region, reads its settings, and writes the document atomically |
| `editor.py`, `tui.py`, `tui_dialogs.py` | The Textual terminal editor |

### Local actions

- **Snapshot.** Treestamp captures the Git index (or a ref given with `--target`) once. Every later action in that run or editing session uses the same snapshot, so files changing on disk do not alter the tree being edited.
- **Read a document.** Treestamp locates exactly one `<!-- treestamp:start -->` / `<!-- treestamp:end -->` pair and parses the tree and the optional `treestamp:config` comment between them.
- **Start or load.** In the terminal editor, **New document** starts a tree for a chosen subtree root. **Load document** reads an existing treestamped document and restores its tree, hidden entries, and settings against the current snapshot.
- **Curate.** The user expands, collapses, hides, and annotates entries, and chooses the drawing style and whether directory counts are shown. Curation changes only in-memory state until the user writes or copies.
- **Write.** `update` and the editor's **Write to existing** render the region and replace only its contents, preserving the surrounding text and line endings. The write is prepared against the content read earlier; if the file changed in the meantime, the write is refused. The new content goes to a temporary file in the same directory, which then replaces the document. **Write new file** creates a new document containing only the region and refuses a path that already exists.
- **Check.** `check` performs the same computation as `update`, prints a unified diff when the document would change, and never writes.
- **Copy.** The editor sends the complete treestamp to a native clipboard command if one is on `PATH`, otherwise to the terminal through OSC 52.

The core package makes no network requests.

## Hosted editor

The service in `web/src/treestamp_web/` adapts the core package to HTTP:

| Module | Responsibility |
| --- | --- |
| `app.py` | Routes, error mapping, security headers, rate limits, and structured logs |
| `links.py` | Parses user-entered repository links into a validated owner, name, and ref |
| `github.py` | GitHub REST client with response-size caps, timeouts, and a shared request budget |
| `cache.py` | Temporary in-memory snapshot retention (one hour per snapshot) |
| `preview.py` | Opens and edits a document against one snapshot |
| `limits.py` | Per-client token-bucket rate limits, held in process memory |
| `proxy.py` | Accepts a visitor address from `CF-Connecting-IP` only when the peer is a configured Cloudflare range |
| `routing.py` | Fly.io session affinity, so a session's requests reach the Machine holding its snapshot |
| `static/` | The browser application, served from the same origin |

### Hosted actions

1. The visitor enters a repository link. The service confirms through the GitHub API that the repository is public, resolves its default branch to a commit and tree, and fetches the complete recursive tree listing. Private repositories, branches, and tags are refused; only the default-branch HEAD or a pinned commit already in the cache can be opened.
2. The service fetches the blobs it needs: symlink targets in the selected subtree, up to a configured limit, and the selected document, up to 1 MiB.
3. The service returns the rendered tree, display rows, and a session state envelope to the browser. The browser holds the curation state; the server keeps only the cached snapshot.
4. Each edit sends the state envelope and one operation to the service, which validates both, applies the operation, and returns the new state. Requests for a snapshot that is no longer cached fail with `410` rather than reading a newer commit.
5. The visitor copies the result to the clipboard.

The service authenticates to GitHub with a token or GitHub App credentials. It logs structured events containing the repository name, commit, result, and request budget, not document contents.

## Build and release

[MAINTENANCE.md](../MAINTENANCE.md) describes CI, releases, PyPI publication, and deployment of the hosted editor.

## External interfaces

The Python modules are not a supported library interface.

### Command line

`treestamp [tui] [PATH] [--document PATH] [--print]` opens the terminal editor on the repository at `PATH` (default `.`). With `--print`, it writes the complete treestamp for `--document` (default `README.md`) to standard output and exits without opening the editor or writing a file. `treestamp` with no command is equivalent to `treestamp tui`.

`treestamp update [DOCUMENT] [--target REF] [--compare REF]` rewrites the marked region of `DOCUMENT` (default `README.md`, relative to the repository root) to match the snapshot. `--target` selects a Git ref instead of the index; `--compare` names a reference used to detect moved paths, so their annotations follow them.

`treestamp check [DOCUMENT] [--target REF] [--compare REF]` reports whether `update` would change the document, printing a unified diff if so.

`treestamp --version` prints the installed version.

Output is UTF-8. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Success, or the document is current |
| 1 | `check` found that the document needs updating |
| 2 | Invalid input or a curation constraint |
| 3 | Git or the filesystem could not supply the required facts |
| 130 | Interrupted |

Errors are written to standard error, prefixed with `treestamp:`.

### Terminal editor

The terminal editor is a keyboard-driven Textual application. Arrow keys, Space, Home, End, and Page Up/Down move through the tree and expand or collapse directories. Other keys perform the actions described under [Local actions](#local-actions): `N` New document, `l` Load document, `h` hide or unhide, `H` reveal hidden entries, `S` unhide all, `a` annotate, `c` show or hide counts, `s` drawing style, `v` preview, `y` copy, `w` Write to existing, `n` Write new file, `p` print the complete treestamp to standard output and exit, `?` help, and `q` or Escape to quit. Document paths entered in its dialogs are relative to the repository root.

### Document format

The [README](../README.md#3-add-it-to-your-readme) shows a complete region and describes its markers, drawing styles, and annotations. A document contains exactly one region.

The optional config comment holds TOML with three keys, each written only when needed: `root`, the repository-relative subtree the tree displays (default `.`); `hidden`, the repository-relative paths of hidden entries; and `special_paths`, the full paths of entries whose names contain the annotation delimiter, so they parse unambiguously. Other keys are rejected. Annotations follow a fixed `  # ` delimiter.

### Pre-commit hooks

`.pre-commit-hooks.yaml` defines `treestamp` (runs `treestamp update`) and `treestamp-check` (runs `treestamp check`). Both run on every commit and receive no filenames.

### Hosted HTTP API

The browser application uses these endpoints. They exist to serve that application and are not a supported public API.

| Endpoint | Input | Output |
| --- | --- | --- |
| `GET /` | None | The browser application |
| `GET /{owner}/{repo}` | A repository owner and name in the path | The browser application, which then opens that repository |
| `GET /api/preview` | Query parameters `url`, or `owner` and `repo`; optional `ref` (a commit id), `root`, `document` | A preview: repository, resolved commit and tree, settings, rendered tree and region, display rows, warnings, permalink, and state envelope |
| `POST /api/preview` | The same fields as a JSON object | The same as `GET` |
| `POST /api/op` | JSON with `owner`, `repo`, `ref` (a 40-character commit id), `root`, `document`, `state` (the envelope), `op` (`type` plus `path` or `text`), and `reveal` | An updated preview |
| `GET /healthz` | None | Liveness, versions, build commit, credential type, last observed GitHub budget, and cache statistics |

The state envelope carries the curation (expanded and hidden paths, annotations, and settings), the source it was created from, the loaded document's original bytes, and a revision counter; the browser returns it unchanged with each operation. Operation types:

| Type | Effect |
| --- | --- |
| `toggle`, `expand`, `collapse` | Change whether the directory at `path` is expanded |
| `hide`, `unhide` | Hide or show the entry at `path` |
| `unhide_all` | Show all hidden entries |
| `annotate` | Set the annotation of `path` to `text`; empty text removes it |
| `present` | Re-render with the settings in the state, such as drawing style or counts |
| `restore` | Re-render the state without counting as an edit, for example after a page reload |

`reveal` controls whether display rows include hidden entries; it does not change the printed tree. Request bodies are limited to 256 KiB. Errors return a JSON object with a stable `code` and a message, using `400`, `404`, `410`, `413`, `422`, `429` (with `Retry-After`), `503`, or `504`.
