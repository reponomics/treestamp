# Treestamp web editor

The web editor loads public GitHub repositories at their default-branch HEAD, edits a frozen snapshot, and exports a treestamp for you to copy into a document. It never writes to a GitHub repository. Failed loads preserve the existing draft. Cached snapshots and their links are temporary; an unavailable snapshot is not silently replaced with another commit.

The service is a FastAPI application using the core Treestamp package. It ships in the hosted container and is not part of the core PyPI distribution. The public web editor uses [treestamp.reponomics.org](https://treestamp.reponomics.org/); see [PRIVACY.md](../PRIVACY.md).

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

```bash
make web-ci
venv/bin/playwright install chromium
make web-browser-test
make web-image
```

`web-ci` runs lint, formatting, strict Python types, Python tests with coverage, and JavaScript tests. Browser tests use the fake GitHub API; pass `BROWSER_FLAGS="--browser-channel chrome"` to use an installed Chrome. Cache and quota tests use controlled clocks and transports.

Bundled welcome examples are offline fixtures. Their responses in `src/treestamp_web/static/example.js` and trees in `src/treestamp_web/data/examples.json` must stay consistent; `tests/test_examples.py` checks them against the API. Opening an example's live repository follows the same public default-branch policy as any other repository.

See [MAINTENANCE.md](../docs/MAINTENANCE.md) for promoting the existing app to production, the separate test deployment, deployment from `main`, and session recovery after cache loss.
