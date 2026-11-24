# treestamp web editor

The web editor loads public GitHub repositories at their default-branch HEAD, edits a frozen snapshot, and exports a treestamp for you to copy into a document. It never writes to a GitHub repository. Failed loads preserve the current treestamp. Cached snapshots and their links are temporary; an unavailable snapshot is not silently replaced with another commit.

The service is a FastAPI application using the core treestamp package. It ships in the hosted container and is not part of the core PyPI distribution. The public web editor uses [treestamp.reponomics.org](https://treestamp.reponomics.org/); see [PRIVACY.md](../PRIVACY.md).

Enter a repository on the landing page and choose **Create treestamp** for a fresh tree at its root, or **Load treestamp** to read its root README.md. **Choose another folder or file…** opens the source picker. **Try example** opens a bundled snapshot of reponomics/treestamp. **Resume session** offers best-effort recovery of recent work while the required cached data remains available. The [UI flow reference](../docs/ui-flow.md) describes navigation, temporary drafts, note transfer, and Discard changes.

Loaded treestamps preserve supported document formatting when copied or restored. See the [document format](../docs/design.md#document-format) for boundary spacing, line endings, and configuration formatting. The [design reference](../docs/design.md#hosted-http-api) describes the browser's session envelope and HTTP operations.

## Run locally

From the repository root:

```bash
make venv
make install
nvm install
nvm use
make web-fake
```

In a second terminal, run `make web-serve` and open `http://127.0.0.1:8000`. The fake GitHub API serves this checkout on port 8100; any `owner/repo` names the same local fixture. This transport is for development only. Use `FAKE_FLAGS=--truncated`, `FAKE_FLAGS="--rate-limit-after 3"`, `FAKE_FLAGS="--delay 5"`, `FAKE_FLAGS=--empty`, or `FAKE_FLAGS="--only owner/repo"` to exercise failure cases.

To use real GitHub, set `GITHUB_TOKEN` or all three GitHub App variables: `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY`. Then run `make web-serve GITHUB_API_URL=https://api.github.com`. To read the token or private key from a separate file instead, set `GITHUB_TOKEN_FILE` or `GITHUB_APP_PRIVATE_KEY_FILE` to its path; each file can be replaced without other configuration changes and takes effect on restart. Keep credentials in a host secret store or a file readable only by the service, never in the repository.

## Symlink resource limits

The hosted service applies three limits to symlinks within the selected subtree. Each can be configured through an environment variable at startup:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SYMLINK_FETCH_LIMIT` | 32 distinct objects | Bounds upstream blob fetches; paths sharing a target blob use one fetch |
| `SYMLINK_TARGET_MAX_BYTES` | 16 KiB (16384 bytes) | Bounds each raw target blob, including cached blobs |
| `SYMLINK_EXPANDED_MAX_BYTES` | 256 KiB (262144 bytes) | Bounds raw target bytes counted once for every symlink path, including repeated references to the same blob |

The byte limits are checked before building or rendering the source tree, on opening and on subsequent edits or note transfers. Exceeding a limit rejects the selected subtree without truncating targets. These are hosted-service constraints; the local CLI and TUI retain their existing behavior.

Counting each reference bounds repeated decoding and the targets' contribution to rendered output: the current codec expands a raw target byte to at most five characters, including list-style escaping. This does not impose a global memory ceiling on the service; other source data and concurrent requests remain subject to their separate limits.

## Test and build

The [shared UI patterns](../docs/ui-patterns.md) define button roles, interaction states, and brand typography. Their CSS is shared across the landing page, picker, editor, and dialogs.

Follow the [testing guide](../docs/testing.md) for hosted quality gates, JavaScript coverage, browser setup and commands, fixture contracts, and known warnings. Build the hosted container with `make web-image`.

The opt-in example and retained example links use bundled offline fixtures. Opening an example's live repository follows the same public default-branch policy as any other repository.

See [MAINTENANCE.md](../docs/MAINTENANCE.md) for promoting the existing app to production, the separate test deployment, deployment from `main`, and session recovery after cache loss.
