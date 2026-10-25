# Interface reference

This document describes the external interfaces of Treestamp's released assets: the `treestamp` package on PyPI and the hosted editor at <https://treestamp.reponomics.org>. Before `1.0`, interfaces and the document format may change between releases; such changes are noted in the [changelog](../CHANGELOG.md). For how the parts fit together, see [design.md](design.md).

## Released assets

| Asset | Interfaces |
| --- | --- |
| `treestamp` package (PyPI) | The `treestamp` command and `python -m treestamp`; the treestamped document format; the pre-commit hooks in this repository. Requires Python 3.11+ and `git` on `PATH`. |
| Hosted editor | A browser page and the JSON HTTP API it uses. Built from [`web/`](../web/) and deployed as a container; not published to PyPI. |

The Python modules in the `treestamp` package are internal. Nothing in the project declares an importable API, and module contents may change in any release. The `treestamp_web` package is not distributed.

## Command line

```
treestamp [path] [--document PATH] [--print]
treestamp tui [path] [--document PATH] [--print]
treestamp check [document] [--target REF] [--compare REF]
treestamp update [document] [--target REF] [--compare REF]
treestamp --version | --help
```

If the first argument is not `tui`, `check`, `update`, `--help`, `-h`, or `--version`, the command is treated as `tui`. `python -m treestamp` is equivalent to `treestamp`.

### `treestamp tui`

| Argument or option | Meaning |
| --- | --- |
| `path` | Location inside the repository to open. Default `.`. The repository root is found with `git rev-parse --show-toplevel`. |
| `--document PATH` | Document path relative to the repository root. Without `--print`, it is the default offered by Load document. With `--print`, that document is loaded and must exist and contain a marker pair. |
| `--print` | Print the complete treestamp to stdout and exit without opening the editor or writing a file. Without `--document`, `README.md` is loaded if it exists and contains a marker pair; otherwise a new tree of the repository root's immediate children is printed. |

The editor reads the Git index. It opens on a choice between New document (enter a tree root relative to the repository root) and Load document (enter a document path). Main keys:

| Key | Action |
| --- | --- |
| Arrows, Space, Home, End, Page Up/Down | Navigate; expand or collapse directories |
| `h`, `S`, `H` | Hide or unhide the entry; unhide all; show or conceal hidden entries in the editor |
| `a` | Edit the entry's annotation |
| `c`, `s` | Toggle counts on collapsed directories; cycle Unicode, ASCII, and list styles |
| `N`, `l` | New document; Load document |
| `n`, `w` | Write a new file (fails if it exists); write into an existing document's marker pair |
| `v`, `y`, `p` | Preview the tree; copy the complete treestamp; print it to stdout and exit |
| `?`, `q`/Esc | Help; quit (confirms if there are unwritten changes) |

Only the two write actions change files. Copy uses `pbcopy`, `clip`, `wl-copy`, `xclip`, or `xsel` when available, otherwise the terminal's clipboard escape sequence.

### `treestamp check` and `treestamp update`

Both commands run from inside the repository and operate on one document.

| Argument or option | Meaning |
| --- | --- |
| `document` | Document path relative to the repository root (not the current directory). Default `README.md`. |
| `--target REF` | Build the target tree from `REF^{tree}` instead of the index. Any local commit or tree reference accepted by `git rev-parse`. |
| `--compare REF` | Detect renames between `REF` and the target with `git diff --find-renames`. An annotation on a renamed file, symlink, or submodule moves to its new path. Only unambiguous renames within the selected root are used. Must be nonempty. |

Both commands update the printed tree against the target: deleted entries are removed, counts are refreshed, new entries under expanded directories are added (new directories collapsed), and expansion, annotations, hidden paths, style, and count visibility are kept. The rendered region is then compared byte for byte with the document.

`check` never writes. `update` replaces the region atomically and leaves everything outside the marker pair unchanged. Neither command stages or commits.

### Output and exit codes

| Command | stdout |
| --- | --- |
| `check`, `update`, document current | `Current: <absolute document path>` |
| `check`, document stale | Unified diff of the document, with the absolute path as both file names |
| `update`, document rewritten | `Updated: <absolute document path>` |
| `tui --print`, `p` in the editor | The complete treestamp, start and end markers included |

Errors are written to stderr as `treestamp: <message>`; argument errors use argparse's usage message. Output is UTF-8 and is written without platform newline translation; the printed treestamp uses LF line endings.

| Exit code | Meaning |
| --- | --- |
| 0 | Success; for `check`, the document is current |
| 1 | `check` only: the document would change |
| 2 | Invalid arguments, document, settings, or paths; a tree that cannot be represented |
| 3 | Git or filesystem failure, including not being in a Git repository or `git` missing from `PATH` |
| 130 | Interrupted |

## Pre-commit hooks

Defined in [`.pre-commit-hooks.yaml`](../.pre-commit-hooks.yaml). Both use `language: python`, `pass_filenames: false`, and `always_run: true`, so they run for every commit regardless of which files changed.

| Hook id | Runs | Effect |
| --- | --- | --- |
| `treestamp-check` | `treestamp check` | Fails when `README.md` needs maintenance. |
| `treestamp` | `treestamp update` | Rewrites `README.md` in the working tree when needed; the result is not staged. |

Arguments given in the hook's `args` are appended, for example a different document path.

## Treestamped document format

A treestamped document is a text file containing one marker pair:

````markdown
<!-- treestamp:start -->
<!-- treestamp:config
root = "src"
hidden = ["src/generated"]
-->
```sh
./
├── app/  # Application code
│   ├── main.py
│   └── routes.py
├── tests/ (12 files)
└── pyproject.toml
```
<!-- treestamp:end -->
````

### Markers

- `<!-- treestamp:start -->` and `<!-- treestamp:end -->` each occupy a whole line, starting in column one. Trailing whitespace is allowed; indented or otherwise altered marker lines are rejected.
- A document has exactly one start marker followed by one end marker. Markers inside fenced code blocks outside the region are ignored.
- A leading UTF-8 byte order mark is ignored. The region is written with the line ending of the start marker line; bytes outside the pair are never changed.
- Empty markers are valid input for Write to existing, which fills the region.

### Configuration comment

An optional `<!-- treestamp:config` line, a TOML payload, and a closing `-->` line may open the region. It is written only when at least one key is needed. Unknown keys are rejected.

| Key | Value |
| --- | --- |
| `root` | Repository-relative directory whose contents the tree shows. Default `.`. |
| `hidden` | Array of repository-relative paths, under `root`, hidden by the user. Each must be a direct child of a printed, expanded directory and must not also be printed. |
| `special_paths` | Array of repository-relative paths of printed entries whose names contain the annotation delimiter. Written automatically so those rows can be read back. |

Paths are TOML strings. A path that is not valid UTF-8 is written as `{git_bytes = "<hexadecimal bytes>"}`. Arrays must not contain duplicates.

### Tree body and styles

The first row is `./`. Rows below use one of three styles; the style is detected from the second row when reading.

| Style | Connectors | Framing |
| --- | --- | --- |
| Unicode | `├── `, `└── `, `│   ` | ```` ```sh ```` fence |
| ASCII | `` |-- ``, `` `-- ``, `|   ` | ```` ```sh ```` fence |
| List | `- ` with two spaces of indentation per level | No fence; Markdown characters in names are backslash-escaped |

When reading, a fence of three or more backticks or tildes with an optional alphabetic info string is accepted.

### Rows

- Directories end in `/`. A collapsed directory may show counts of its immediate children, for example `(3 files, 1 folder)`, with zero parts omitted. Counts include hidden children. Either every collapsed directory shows counts or none do.
- Symbolic links print as `name -> target`, or `name -> null` when the target is unknown. Submodules print as `name [gitlink]`. Both are leaves.
- Children are ordered directories first, then by the UTF-8 bytes of the name.
- An annotation follows the delimiter `  # ` (two spaces, `#`, space). Annotations are a single line of printable text; tabs become two spaces.
- Control characters, backslashes, line and paragraph separators, trailing whitespace, and bytes that are not UTF-8 are escaped in names and targets as `\\`, `\n`, `\t`, `\r`, `\xNN`, or `\uNNNN`.
- Counts and symlink targets are regenerated from Git; annotations, expansion, and hiding are the saved curation.

Before output is written or copied, it is parsed back and must reproduce every path, kind, target, count, and annotation. A tree that cannot meet this is rejected with exit code 2 (or `422 curation` in the hosted editor).

### Path rules

- Tree paths are relative, use `/`, contain no empty, `.`, or `..` components or NUL bytes, and are at most 128 components deep. A tree may contain at most 200,000 entries.
- Document paths given to the CLI are relative to the repository root, with no absolute paths, drive letters, `~`, or `..`. They must not pass through a symbolic link, a nested repository, or a submodule, and an existing document must be a regular file.
- Configuration paths are relative to the repository root even when `root` selects a subtree.

## Hosted editor HTTP interface

The service is not versioned separately and its API is designed for its own page. All responses carry `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Cache-Control: no-cache` unless a route sets its own caching.

### Pages and static files

| Route | Response |
| --- | --- |
| `GET /` | The editor page. It opens a bundled example. |
| `GET /{owner}/{repository}` | The editor page, which loads that public repository's default branch. `repository` may be `name@<40-hex commit>` to reopen a cached snapshot. Query parameters `root` and `document`, and a fragment `#s=<base64url JSON session envelope>`, restore a session. A first segment of `api`, `static`, `healthz`, or `favicon.ico` returns `404 not_found`. |
| `GET /static/...` | Page assets. |
| `GET /favicon.ico` | Icon, `Cache-Control: public, max-age=86400`. |

### `GET /healthz`

Returns `200` with:

| Field | Value |
| --- | --- |
| `status` | `"ok"` |
| `package`, `web` | Installed `treestamp` and `treestamp-web` versions |
| `build_commit` | Commit the image was built from |
| `credential`, `token_configured` | `"app"`, `"token"`, or `"none"`; whether a credential is configured |
| `budget` | GitHub rate-limit `limit`, `remaining`, and `reset` as last observed |
| `cache` | `trees`, `tree_rows`, `blobs`, and `refs` currently retained |

### `GET /api/preview` and `POST /api/preview`

Opens a repository snapshot and an optional document. Parameters come from the query string (GET) or a JSON object (POST). Unknown parameters are rejected.

| Parameter | Meaning |
| --- | --- |
| `url` | `owner/repo`, `github.com/owner/repo`, or an `https://github.com/owner/repo/...` link, at most 2048 characters. A `/tree/<commit>` or `/commit/<commit>` suffix pins a commit; other suffixes are ignored with a warning. Takes precedence over `owner` and `repo`. |
| `owner`, `repo` | Repository components, used when `url` is absent. |
| `ref` | `HEAD` (default) or a 40-character commit id. Branch and tag names are rejected. |
| `root` | Repository-relative tree root. Default `.`. Replaced by the document's `root` when a document is loaded. |
| `document` | Repository-relative document path. Default `README.md`, loaded only if it exists and contains a marker pair. A nonempty value must exist. An empty string starts a new tree without reading a document. |

In a POST body, values are strings; `root` and `document` may also be `{"git_bytes": "<hex>"}`.

The service reads only public repositories (`private: false`, `visibility: public`) at the default branch head. A pinned commit is served from the cache if present; otherwise it is accepted only if it is still the default branch head, and `410 snapshot_unavailable` is returned if not.

A successful response is a JSON object:

| Field | Value |
| --- | --- |
| `repository` | `owner`, `name`, `url`, `default_branch` |
| `ref` | `requested`, resolved `commit`, and `tree` id |
| `root`, `document` | Selected root and document path |
| `loaded`, `dirty`, `notice` | Whether a document region was loaded; whether the output differs from it; `"Treestamp updated"` when a loaded tree changed |
| `settings` | `root`, `style` (`unicode`, `ascii`, or `list`), `show_counts` |
| `entries`, `root_children` | Entries in the selected tree; printed children of its root |
| `tree`, `region` | The printed tree alone; the complete treestamp with markers |
| `warnings` | Notices, for example an ignored link suffix |
| `permalink` | `/{owner}/{repo}@{commit}` with `root` and `document` query parameters; absolute when `PUBLIC_BASE_URL` is set |
| `state` | Session envelope: `version` (1), `curation` (`settings`, `expanded`, `hidden`, `annotations`), `source` (`owner`, `repo`, `commit`, `root`, `document`), `baseline` (base64 of the loaded region, or null), `generation`, `revision` |
| `rows` | Visible rows: `path`, `key`, `name`, `kind`, `depth`, `annotation`, `hidden`; directories add `collapsed`, `files`, `dirs`, `counts`; symlinks add `target` |

When session routing is enabled, a successful load also sets the cookie `__Host-treestamp-machine` (Secure, HttpOnly, SameSite=Lax) and `Cache-Control: private, no-store`.

### `POST /api/op`

Applies one editing operation to a session. The JSON body:

| Field | Meaning |
| --- | --- |
| `owner`, `repo` | Repository, as in the session source |
| `ref` | The session's 40-character commit id |
| `root`, `document` | As in the session source |
| `state` | The envelope from the previous response; `curation.settings` may carry a new `style` or `show_counts` |
| `op` | `{"type": ..., "path": ..., "text": ...}` |
| `reveal` | Boolean; include hidden rows in `rows`, marked `hidden: true` |

| Operation | Effect |
| --- | --- |
| `restore` | Re-render the state without counting an edit |
| `present` | Re-render the state as an edit (used after a style or count change) |
| `toggle`, `expand`, `collapse` | Change a directory's expansion |
| `hide`, `unhide` | Hide an entry; unhide an entry and its ancestors |
| `unhide_all` | Remove all hiding |
| `annotate` | Set `text` as the entry's annotation; empty text removes it |

`state.source` must match the request fields and the snapshot must still be cached on the serving process, or be a bundled example; otherwise the response is `410 snapshot_unavailable`. The response has the same shape as `/api/preview`, with `revision` incremented for every operation except `restore`.

### Errors

Errors are JSON:

```json
{"error": {"code": "rate_limited", "message": "too many requests from this client", "retry_after": 12}}
```

`retry_after` and a matching `Retry-After` header appear on `429` and `503` responses.

| Status | Code | Cause |
| --- | --- | --- |
| 400 | `invalid_link`, `invalid_settings`, `invalid_op`, `invalid_state` | Malformed link, parameter, operation, or session envelope |
| 404 | `not_found` | Repository missing, private, moved, empty, or inaccessible; explicit document missing; reserved page path |
| 410 | `snapshot_unavailable` | The session's snapshot is no longer retained, or a pinned commit is no longer the default branch head |
| 413 | `state_too_large` | Request body over the state limit |
| 413 | `too_large` | GitHub listing truncated or over limits; snapshot exceeds cache limits |
| 422 | `curation` | Document region invalid, document not a regular file or over 1 MiB, root not a directory, or tree not representable |
| 422 | `source_unavailable` | The subtree needs more symlink targets than the service fetches |
| 429 | `rate_limited` | Per-client limit reached |
| 503 | `upstream_unavailable` | GitHub error, rate limiting, rejected credential, or the service's GitHub budget reserve reached |
| 504 | `upstream_timeout` | GitHub did not answer in time |

### Limits

| Limit | Default |
| --- | --- |
| Request body | 262,144 bytes |
| Loads per client | 20 per minute |
| Operations per client | 240 per minute |
| Snapshot retention | 1 hour after the most recent load of that commit, not extended by operations |
| Document size | 1 MiB |
| Tree listing | 200,000 entries, 32 MiB response, and not truncated by GitHub |
| Symlink targets per load | 32 |
| Other GitHub responses | 4 MiB |

Limits apply per process; production runs two Machines. Several are configurable below.

## Hosted service configuration

These environment variables are operator configuration for running the service, not part of the public interface. They are read once at startup; empty values count as unset; booleans accept `1`, `true`, `yes`, `0`, `false`, or `no`. Production values are in [`web/fly.toml`](../web/fly.toml), and credentials are kept in Fly secrets.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | Listening port used by the container command |
| `GITHUB_TOKEN` | unset | Token credential for GitHub |
| `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY` | unset | GitHub App credential; all three together. The key is PEM; literal `\n` sequences are converted to newlines. Takes precedence over `GITHUB_TOKEN`. |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub API base URL |
| `GITHUB_RATE_RESERVE` | `100` | Refuse GitHub calls when remaining requests fall below this or a tenth of the limit, whichever is smaller |
| `REQUEST_TIMEOUT_SECONDS` | `20.0` | GitHub request timeout |
| `SYMLINK_FETCH_LIMIT` | `32` | Symlink targets fetched per load |
| `CACHE_MAX_TREES`, `CACHE_MAX_ENTRIES`, `CACHE_MAX_BLOBS`, `CACHE_MAX_BLOB_BYTES` | `256`, `2000000`, `4096`, `67108864` | Snapshot cache limits; least recently used snapshots are evicted |
| `RATE_LIMIT_PER_MINUTE`, `OP_RATE_LIMIT_PER_MINUTE` | `20`, `240` | Per-client limits for loads and operations; `0` disables |
| `MAX_STATE_BYTES` | `262144` | Request body limit |
| `TRUST_PROXY`, `CLIENT_IP_HEADER` | `false`, `X-Forwarded-For` | Take the client address from the first value of this header |
| `CLOUDFLARE_PROXY_CIDRS` | unset | Comma-separated Cloudflare ranges. Requires `TRUST_PROXY=1` and `CLIENT_IP_HEADER=Fly-Client-IP`; `CF-Connecting-IP` is then used only when the Fly peer is in these ranges. |
| `FLY_SESSION_ROUTING`, `FLY_MACHINE_ID` | `false`, unset | Cookie-based routing to the Machine holding a session; requires a valid machine id and `MAX_STATE_BYTES` of at most 1,000,000 |
| `PUBLIC_BASE_URL` | unset | Makes permalinks absolute |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, or `error` |
| `BUILD_COMMIT` | `unknown` | Reported by `/healthz`; set at image build |
