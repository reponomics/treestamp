# Treestamp web editor

The web editor loads public GitHub repositories at their default-branch HEAD, edits a frozen snapshot, and exports a treestamp for you to copy into a document. It never writes to a GitHub repository. Failed loads preserve the current tree. Cached snapshots and their links are temporary; an unavailable snapshot is not silently replaced with another commit.

The service is a FastAPI application using the core Treestamp package. It ships in the hosted container and is not part of the core PyPI distribution. The public web editor uses [treestamp.reponomics.org](https://treestamp.reponomics.org/); see [PRIVACY.md](../PRIVACY.md).

The browser remembers your current tree and automatically restores it when you return to the app or the same repository's bare URL. Explicit session links and URL settings take precedence. Opening another tree replaces the saved session. Saving and restoring happen in the background, without routine status messages or a storage-management control. Restoration uses the captured commit and requires its server snapshot to remain available. Successful edits renew the snapshot's one-hour retention period; restoring or viewing alone does not. Cache eviction, expiry, or a service restart can require a fresh repository load. Browser storage supports short return visits and is not durable backup storage.

First-time visitors choose a repository and an entry in its tree before the editor opens. A selected folder starts a new treestamp; **Load treestamp from document** loads an existing one. A document without markers shows a warning and remains selected; it does not redirect into creation or move selection to its parent. **Explore an example** opens one curated tree directly. The decision, arrival rules, and product hypothesis are documented in [UI flow](../docs/ui-flow.md).

Loaded trees retain supported boundary spacing, line endings, and unchanged TOML configuration text when copied or restored. New regions use spaced boundaries, and new or changed configuration arrays use compact wrapping at an 80-character target. Regenerating configuration drops comments inside it. The shared policy and implementation are recorded in [ADR 0002](../docs/adr/0002-formatter-compatible-documents.md).

When a freshly loaded document contains notes whose paths disappeared, the app offers to place them before editing. One source item stays above the destination tree. Select a destination and press Enter to place it, S to skip it, or U to undo the previous decision. Placing a directory also transfers notes at matching relative paths, recursively; unmatched or conflicting descendants stay in the queue. Placement is optional and happens once per document load. Restoring a saved draft opens the editor directly.

Placement uses `POST /api/placement` against the already captured snapshot. Requests carry the original opening envelope, a bounded decision log, and separate browsing expansion/reveal settings. Intermediate results remain provisional in the browser; finishing or declining accepts the result and replaces the saved draft. Browsing destinations does not change the draft's folds or exclusions. Like editing, placement reports an expired snapshot rather than fetching another commit.

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

## Test and build

Follow the [testing guide](../docs/testing.md) for hosted quality gates, JavaScript coverage, browser setup and commands, fixture contracts, and known warnings. Build the hosted container with `make web-image`.

The opt-in example and retained example links use bundled offline fixtures. Opening an example's live repository follows the same public default-branch policy as any other repository.

See [MAINTENANCE.md](../docs/MAINTENANCE.md) for promoting the existing app to production, the separate test deployment, deployment from `main`, and session recovery after cache loss.
