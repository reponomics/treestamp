# Maintenance

These procedures require a full Git checkout, including the hosted application in `web/`. Use the environment and contributor setup in [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md). Run `make help` for available commands. Stage source changes before updating the README tree because Treestamp reads the Git index.

## Validate and build

```bash
make ci web-ci docs-check
make web-browser-test
make build metadata-check distribution-check
make integration-check
```

Browser checks require the separate browser dependencies described in [the web README](https://github.com/reponomics/treestamp/blob/main/web/README.md). `metadata-check` validates both distributions against the approved file set and reports their hashes. `distribution-check` installs the wheel and source archive into fresh environments and exercises headless commands and the terminal editor. After committing a candidate, `make hook-check` checks the public pre-commit hooks from that exact HEAD. Clear `dist/` before building so the checks read only the new artifacts.

## Dependencies and toolchain

The core and hosted projects share `uv.lock`. `make install` installs locked dependencies and build tools into `venv`, then builds the local editable packages without isolated dependency resolution. `make build` synchronizes that locked toolchain before building. Docker selects only the hosted runtime dependencies and operational TLS tools from the same lock, builds both local wheels with the locked build group, and installs those wheels offline. Third-party dependencies must have compatible wheels; the controlled install fails rather than resolving unpinned build dependencies for a source archive.

The uv version is pinned in `.tool-versions`, checked by the Makefile, and read by CI. Docker uses the matching version and image digest. Update those together, including when Dependabot proposes an update to the Docker image; Dependabot does not maintain the `.tool-versions` pin. Keep pip at least `26.2.2`, certifi at least `2026.10.19`, and uv at least `0.13.4` for the eMudhra certificate incident. Continue updating the pinned Python base image, whose system certificate store the Python lock does not manage. The Docker build checks certificate stores, and `make tls-check` performs the same check locally.

Review Dependabot's lock updates by running the quality gates and container checks. Release Please also updates the two local package versions in the lock. The clean-distribution checks intentionally use pip to resolve the published dependency ranges outside the workspace, testing consumer compatibility separately from the locked development environment.

## Repository and release setup

Use `main` as the default branch and require pull requests and signed commits. PRs should require checks including regression tests, compatibility, and vulnerability scanning. Production deployment, Release Please, and PyPI publication do not run on ordinary PRs and should not be required PR checks. Immutable releases are enabled. CodeQL uses GitHub's default setup with the extended query suite for Python, JavaScript/TypeScript, and GitHub Actions, managed in the repository's code scanning settings. Do not enable an advanced CodeQL workflow alongside default setup: GitHub rejects its analysis uploads.

Release Please manages the core and hosted versions together, updates `CHANGELOG.md`, and creates version tags and GitHub Releases after its release PR is merged. The published-release event runs the PyPI workflow, which validates the tag, versions, and commit on `main`, builds and tests fresh distributions, and publishes them with attestations through PyPI Trusted Publishing, configured for this repository's `publish.yml` in the `pypi` environment. No PyPI token is stored. Production deployment has its own trigger and does not wait for a package release.

The workflows and the hosted editor use these settings:

| Setting | Location | Purpose |
| --- | --- | --- |
| `RELEASE_APP_CLIENT_ID` | Repository variable | GitHub App used by Release Please |
| `RELEASE_APP_PRIVATE_KEY` | Repository secret | Private key for that App |
| `PYPI_PUBLISH_ENABLED=true` | Repository variable | Enables PyPI publication |
| `pypi` | GitHub environment | Publication approvals and PyPI's trusted identity |
| `FLY_DEPLOY_ENABLED=true` | Repository variable | Enables production deployment on pushes to `main` |
| `FLY_API_TOKEN` | Secret in the `production` environment | Deploy token scoped to the production Fly app |
| `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY` | Fly secrets on each hosted app | GitHub App the hosted editor uses to read public repositories |

The release App is installed only on `reponomics/treestamp`, with write access to contents, issues, and pull requests. Its token lets release PRs trigger CI and GitHub Releases trigger publication. The hosted editor's App is separate from it. Review the protections of the `pypi` and `production` environments against [GOVERNANCE.md](GOVERNANCE.md).

## Secrets and credentials

Secrets are stored only in the services that use them, as listed in the table above. They are never committed to the repository, built into images, or written to logs. The maintainer keeps the GitHub App private keys outside the repository. Prefer credentials that need no stored secret, such as PyPI Trusted Publishing, and scope each credential to one app or repository.

Only the maintainer can read or change these secrets (see [GOVERNANCE.md](GOVERNANCE.md)). Workflows receive a secret only in the job that needs it, and deployment credentials only through the `production` environment. To install or rotate a hosted app's GitHub App credentials, run `make fly-secrets` with `FLY_CONFIG` set to that app's configuration and the key file in `GITHUB_APP_PRIVATE_KEY_FILE`.

Credentials have no fixed rotation schedule. Rotate a credential immediately if it may have been exposed, and rotate the affected credentials whenever the people with access to them change. After rotating, revoke the old credential and confirm that the workflow or service using it still works.

## Production deployment

[`web/fly.toml`](https://github.com/reponomics/treestamp/blob/main/web/fly.toml) configures production at `https://treestamp.reponomics.org`, served by the Fly app `treestamp-preview`; test deployments use a separate app (see [Preview deployment](#preview-deployment)). [`deploy.yml`](https://github.com/reponomics/treestamp/blob/main/.github/workflows/deploy.yml) deploys every push to `main`, including merged PRs. Required PR checks are the merge gate; deployment does not wait for post-merge CI and never runs on PR events. Leave Fly-native auto-deployment disabled to avoid duplicate rollouts.

To deploy another revision, select **Actions → Deploy production editor → Run workflow**, keep the workflow branch at `main`, and enter a branch, tag, or commit in `revision`, for example `gh workflow run deploy.yml --ref main -f revision=vX.Y.Z`. The workflow runs from `main` to keep its environment policy; the selected revision must provide the production Makefile target and configuration. `make fly-production-deploy FLY_DEPLOY_FLAGS=--remote-only` deploys the current checkout directly.

Deployments are serialized without cancelling an active rollout. A queued automatic run skips its commit if a newer one is already on `main`; a manual run does not. Branches and tags resolve to a fixed commit at checkout, recorded in the workflow summary; use a full commit SHA when the target must be fixed before the run starts. The final health probe checks that the public domain serves the resolved commit. A failed probe reports failure but does not roll back.

Production runs two Machines with Fly's high-availability provisioning. Rolling deployment replaces one Machine at a time and checks `/healthz`; a build failure stops before rollout, and a failed health check can halt it. With `FLY_SESSION_ROUTING=true`, a session cookie routes each editing session to the Machine holding its snapshot. A Machine failure, restart, or deployment can require a fresh load; the browser draft stays copyable and is replaced only after a successful load. Snapshots and quotas are per Machine, so changing the Machine count changes aggregate capacity and limits.

After a deployment, check that `/healthz` reports the deployed `build_commit`, exercise loading, editing, copying, and draft preservation after a failed load in a browser, and run the smoke test against a public repository with a local checkout of the commit the hosted session loads:

```bash
make fly-smoke SMOKE_URL=https://treestamp.reponomics.org \
    SMOKE_REPO=OWNER/REPOSITORY SMOKE_CHECKOUT=/path/to/checkout
```

For rollback, prefer a reviewed revert on `main` through the same checks; the manual workflow rebuilds source and does not restore a previous image. An urgent rollback can redeploy a previously verified image with current certificate stores, followed by the same checks. After a rollback or hotfix deployment, reconcile `main` or disable deployment, because the next push to `main` replaces it.

The domain's DNS records are in Cloudflare's `reponomics.org` zone, without proxying. Recheck them with `flyctl certs setup treestamp.reponomics.org --app treestamp-preview` if the app changes, and check the certificate with `flyctl certs check treestamp.reponomics.org --app treestamp-preview`. Enable proxying only after deploying a revision with Cloudflare peer validation, then use Full (strict) TLS, keep HTML, API, and `/healthz` responses out of the edge cache (no Cache Everything rule), and review `CLOUDFLARE_PROXY_CIDRS` against [Cloudflare's published ranges](https://www.cloudflare.com/ips/). See [Fly's custom-domain instructions](https://docs.fly.io/networking/custom-domain) and [Cloudflare guidance](https://docs.fly.io/networking/understanding-cloudflare).

## Preview deployment

`web/fly.preview.toml` targets `reponomics-treestamp-preview`, a test deployment of the web editor that has not been deployed yet. Install its own GitHub App credentials before its first deployment. Preview deployment is manual and runs one Machine that may stop when idle:

```bash
make web-image
make fly-preview-deploy
make fly-status FLY_CONFIG=web/fly.preview.toml
```

Deploy a clean, committed revision so its build identifier describes the deployed files, then verify it as for production with `SMOKE_URL=https://reponomics-treestamp-preview.fly.dev`.

## Open setup tasks

- [ ] Deploy a reviewed revision to production and verify two-Machine session routing and draft recovery.
- [ ] Enable Cloudflare proxying with Full (strict) TLS, then verify cache behavior and rerun the domain and smoke checks.
- [ ] Configure credentials for `reponomics-treestamp-preview` and deploy it before using it for previews.
- [ ] Publish the product page and demos from the separate `reponomics-web` repository, then link them from this project.

## README tree and alternate styles

The README contains one managed treestamp. Its ASCII and list previews are generated from that tree by `scripts/readme_styles.py`, preserving its curation, annotations, counts, and footer setting. The preview region has separate `readme-styles` markers so the normal document parser still sees only one managed treestamp.

After editing the tree or changing tracked paths, run `make readme-update` to refresh the main tree and both previews. Stage new files first because the tree uses the Git index. `make integration-check` verifies both the repository tree and the generated previews without writing. The README freshness workflow, local pre-commit check, and automatic README update workflow use these same commands.
