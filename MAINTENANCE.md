# Maintenance

These procedures require a full Git checkout, including the hosted application in `web/`. Use the environment and contributor setup in [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md). Run `make help` for available commands. Stage source changes before updating the README tree because Treestamp reads the Git index.

## Validate and build

```bash
make ci web-ci docs-check
make web-browser-test
make build metadata-check distribution-check
make integration-check
```

Browser checks require the separate browser dependencies described in [the web README](https://github.com/reponomics/treestamp/blob/main/web/README.md). `metadata-check` validates both distributions against the approved file set and reports their hashes. `distribution-check` installs the wheel and source archive into fresh environments and exercises headless commands and the terminal editor. After committing a candidate, `make hook-check` checks the public pre-commit hooks from that exact HEAD.

Build release artifacts from a clean, reviewed revision. Inspect the archive contents before publication; internal notes and unrelated products do not belong in either distribution. Remove or archive older files from `dist/` before a release build so checks and uploads cannot select stale artifacts.

## Release status

The initial package version is `0.1.0`; it has not been published. Release Please will manage version changes, `CHANGELOG.md`, tags, and GitHub Releases. PyPI publication will follow those releases through GitHub Trusted Publishing. Those workflows and repository settings still need to be configured in the new public repository; the current checks do not publish packages.

Before the first release, create the public remote, enable private vulnerability reporting, configure the release automation and PyPI publisher, and run the checks on the actual release revision. Keep the core and hosted package versions aligned. Release notes should explain changes that require action, including format changes before `1.0`.

## Preview deployment

The checked-in `web/fly.toml` targets `treestamp-preview`. Deployment is manual and uses the commit at HEAD for the health endpoint's build identifier:

```bash
make web-image
make fly-deploy
make fly-status
```

Deploy a clean, committed candidate so that identifier describes the deployed files. The Docker build checks certificate stores; `make tls-check` performs the corresponding check in the local Python environment. Credentials belong in the host's secret store, not in Git.

Check `https://treestamp-preview.fly.dev/healthz`, then run the public-repository smoke test with a matching local checkout:

```bash
make fly-smoke SMOKE_URL=https://treestamp-preview.fly.dev \
    SMOKE_REPO=OWNER/REPOSITORY SMOKE_CHECKOUT=/path/to/checkout
```

The repository must be public, and the local checkout must contain the commit used by the hosted session. Verify loading, editing, copying, and draft preservation after failed loads in a browser. For rollback, redeploy a previously verified image with up-to-date certificate stores and recheck the build identifier and smoke test.

A separate production Fly app and `treestamp.reponomics.org` are planned. Production deployment will follow successful checks on pushes to `main`; it is separate from PyPI releases. Cloudflare routing and trusted visitor-IP handling must be configured together before enabling its proxy. These production settings are not established by the preview configuration.
