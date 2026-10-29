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

## Dependency and installer maintenance

The core and hosted projects share `uv.lock`. `make install` installs locked dependencies and build tools into `venv`, then builds the local editable packages without isolated dependency resolution. `make build` synchronizes that locked toolchain before building. Docker selects only the hosted runtime dependencies and operational TLS tools from the same lock, builds both local wheels with the locked build group, and installs those wheels offline. Third-party dependencies must have compatible wheels; the controlled install fails rather than resolving unpinned build dependencies for a source archive.

The uv version is pinned in `.tool-versions`, checked by the Makefile, and read by CI. Docker uses the matching version and image digest. Update those together, including when Dependabot proposes an update to the Docker image; Dependabot does not maintain the `.tool-versions` pin. Keep pip at least `26.2.2`, certifi at least `2026.10.19`, and uv at least `0.13.4` for the eMudhra certificate incident. Continue updating the pinned Python base image and checking its system certificate store; the Python dependency lock does not manage operating-system certificates.

Dependabot proposes uv dependency updates. Review lock changes with their declarations, run the quality gates and container checks, and commit both together. Release Please also updates the two local package versions in the lock. The clean-distribution checks intentionally use pip to resolve the published dependency ranges outside the workspace; they test consumer compatibility separately from the locked development environment. Revert a dependency change by reverting its declarations and lock together, then synchronizing the environment again.

## Repository and release setup

Use `main` as the default branch and require pull requests and signed commits. After the checks have run in the repository, select these required PR check names:

- `Regression suite (Linux, Python 3.11)`
- `Regression suite (Linux, Python 3.12)`
- `Regression suite (Windows, Python 3.11)`
- `Regression suite (Windows, Python 3.12)`
- `Hosted editor (Linux, Python 3.11)`
- `README tree freshness`
- `Validate PR title`

Production deployment, Release Please, and PyPI publication do not run on ordinary PRs and should not be required PR checks. Enable immutable GitHub Releases before the first release. CodeQL uses GitHub's default setup with the extended query suite for Python, JavaScript/TypeScript, and GitHub Actions, managed in the repository's code scanning settings. Do not enable an advanced CodeQL workflow alongside default setup: GitHub rejects its analysis uploads. Scorecard runs only when the repository is public; OSV scans resolved Python dependencies while private, retaining its report in Actions without uploading it to code scanning.

Release Please manages the core and hosted versions together, updates `CHANGELOG.md`, and creates version tags and GitHub Releases after its release PR is merged. The published-release event runs the PyPI workflow, which validates the tag, versions, and commit on `main`, builds and tests fresh distributions, and publishes them with attestations through Trusted Publishing. Website deployment has its own trigger and does not wait for a package release.

Configure these GitHub settings before enabling publication or production deployment:

| Setting | Location | Purpose |
| --- | --- | --- |
| `RELEASE_APP_CLIENT_ID` | Repository variable | GitHub App used by Release Please |
| `RELEASE_APP_PRIVATE_KEY` | Repository secret | Private key for that App |
| `PYPI_PUBLISH_ENABLED=true` | Repository variable | Enables PyPI publication once the repository is public |
| `pypi` | GitHub environment | Publication approvals and PyPI's trusted identity |
| `FLY_DEPLOY_ENABLED=true` | Repository variable | Enables independent production deployment on pushes to `main` |
| `FLY_API_TOKEN` | Secret in the `production` environment | Deploy token scoped to the production Fly app |

Install the release App on the selected `reponomics/treestamp` repository with write access to contents, issues, and pull requests. Its token lets release PRs trigger CI and GitHub Releases trigger publication. The App does not need organization-wide repository access. The `pypi` environment exists; review its protections and those of `production` against the maintainers' approval policy. Publication runs from release tags, while deployment runs from `main`.

In PyPI, configure a [pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) for project `treestamp`, GitHub owner `reponomics`, repository `treestamp`, workflow filename `publish.yml`, and environment `pypi`. No long-lived PyPI upload token is needed. A pending publisher does not reserve the package name.

## Secrets and credentials

Secrets are stored only in the services that use them: GitHub repository secrets and environments for the workflows, and Fly.io secrets for the hosted editor, as listed in [Repository and release setup](#repository-and-release-setup) and [Production deployment](#production-deployment). They are never committed to the repository, built into images, or written to logs. The maintainer keeps the GitHub App private keys outside the repository. Prefer credentials that need no stored secret, such as PyPI Trusted Publishing, and scope each credential to one app or repository.

Only the maintainer can read or change these secrets (see [GOVERNANCE.md](GOVERNANCE.md)). Workflows receive a secret only in the job that needs it, and deployment credentials only through the `production` environment.

Credentials have no fixed rotation schedule. Rotate a credential immediately if it may have been exposed, and rotate the affected credentials whenever the people with access to them change. After rotating, revoke the old credential and confirm that the workflow or service using it still works.

## First release and subsequent releases

The first release is configured as `0.1.0`. Complete these steps in order:

1. Merge the automation setup to `main`, configure the release App, enable immutable releases, and configure the `pypi` environment and Trusted Publisher.
2. Finish the public-content review, make the repository public, enable private vulnerability reporting, and set `PYPI_PUBLISH_ENABLED=true`.
3. Review Release Please's first release PR. Confirm that both project versions and its manifest say `0.1.0`. Consolidate the existing `0.1.0 (Unreleased)` notes into the generated dated release section so the changelog describes the release once.
4. After its required checks pass, merge that release PR. Release Please creates the tag and GitHub Release; the publication workflow validates and uploads the package. Verify the PyPI files, installation, and attestations.

Do not merge the first release PR before publication is ready: a release created while the repository is private or publication is disabled will not publish automatically when those settings change later. Subsequent releases follow the same release-PR process. Explain changes requiring user action in the changelog, including format changes before `1.0`.

Published versions are immutable. Correct a released package through a later release; do not move its tag, delete and recreate its release, or upload changed files under the same version. If a publication run fails, inspect which artifacts reached PyPI before retrying it.

## Production deployment

[`web/fly.toml`](https://github.com/reponomics/treestamp/blob/main/web/fly.toml) promotes the existing `treestamp-preview` Fly app to production at `https://treestamp.reponomics.org`. Future previews use the separate `reponomics-treestamp-preview` app. Leave `FLY_DEPLOY_ENABLED` unset until production deployment, session routing, and custom-domain checks succeed.

Keep the production app's GitHub API credentials in Fly secrets: either `GITHUB_TOKEN` or `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY`. To install or rotate the App credentials, `make fly-secrets` accepts `FLY_CONFIG=web/fly.toml` and reads the key from `GITHUB_APP_PRIVATE_KEY_FILE`. These service credentials are separate from the App used by Release Please.

Deploy a clean, reviewed commit on `main` manually for the initial setup:

```bash
make fly-production-deploy FLY_DEPLOY_FLAGS=--remote-only
make fly-status FLY_CONFIG=web/fly.toml
```

Production keeps two Machines running; the production target enables Fly's high-availability provisioning. Rolling deployment replaces at most one Machine at a time and checks `/healthz` during rollout. A build failure stops before rollout. A failed health check can halt rollout, but it is not a guarantee against application bugs or interrupted editing sessions. With `FLY_SESSION_ROUTING=true`, a browser-session cookie uses Fly's `FLY_MACHINE_ID` to route an active editing session to its cached snapshot. Sessions are temporary. A Machine failure, restart, or deployment can require a fresh URL load; the existing browser draft stays copyable and is replaced only after a successful load. Snapshots and quotas remain process-local, so changing the Machine count changes aggregate capacity and limits.

The custom domain is attached to `treestamp-preview` in Fly. These records are saved in Cloudflare for the `reponomics.org` zone, with proxying disabled. Fly reports the certificate as Ready, with active RSA and ECDSA certificates and successful validations:

| Type | Name | Value | Cloudflare proxy |
| --- | --- | --- | --- |
| CNAME | `treestamp` | `8w9r381.treestamp-preview.fly.dev` | DNS only; enable after the reviewed production deployment |
| TXT | `_fly-ownership.treestamp` | `app-8w9r381` | Not applicable |
| CNAME | `_acme-challenge.treestamp` | `treestamp.reponomics.org.8w9r381.flydns.net` | DNS only |

Recheck the records with `flyctl certs setup treestamp.reponomics.org --app treestamp-preview` if the app changes, and check certificate status with `flyctl certs check treestamp.reponomics.org --app treestamp-preview`. Keep proxying disabled until a reviewed `main` deployment includes Cloudflare peer validation; then enable it with Full (strict) TLS and complete the checks below. See [Fly's custom-domain instructions](https://docs.fly.io/networking/custom-domain) and [Cloudflare guidance](https://docs.fly.io/networking/understanding-cloudflare).

Keep HTML, API, and `/healthz` responses out of Cloudflare's edge cache; do not apply a Cache Everything rule to this hostname. The application accepts `CF-Connecting-IP` only when Fly's peer address belongs to the configured Cloudflare ranges. Worker subrequests and invalid visitor headers fall back conservatively to the peer for rate limiting. Review `CLOUDFLARE_PROXY_CIDRS` against [Cloudflare's published ranges](https://www.cloudflare.com/ips/) when maintaining this configuration, and keep the service behind Fly ingress.

Check `/healthz` through the custom domain and confirm that `build_commit` matches the deployed commit. Exercise loading, editing, copying, and draft preservation after failed loads in a browser, then run a public-repository smoke test with a matching local checkout:

```bash
make fly-smoke SMOKE_URL=https://treestamp.reponomics.org \
    SMOKE_REPO=OWNER/REPOSITORY SMOKE_CHECKOUT=/path/to/checkout
```

Store an app-scoped Fly deploy token as `FLY_API_TOKEN` in the GitHub `production` environment, then enable `FLY_DEPLOY_ENABLED`. The separate [`deploy.yml`](https://github.com/reponomics/treestamp/blob/main/.github/workflows/deploy.yml) workflow deploys pushes to `main`, including merged PRs. Required PR checks are the merge gate; deployment does not wait for post-merge CI, and a failure in the separate CI workflow does not cancel it. Deployment never runs on PR events. No repository connection or auto-deploy setting in Fly is needed; leave Fly-native auto-deployment disabled to avoid duplicate rollouts. Cloudflare supplies DNS and proxying, while GitHub Actions invokes Fly to build and deploy the application.

To deploy manually through GitHub Actions, select **Actions → Deploy production editor → Run workflow**, leave the workflow branch set to `main`, and enter the branch, tag, or commit to deploy in `revision` (default: `main`). For example, `gh workflow run deploy.yml --ref main -f revision=v0.1.0` rebuilds and deploys that release, while `-f revision=hotfix/example` selects a hotfix branch. The workflow runs from `main` to retain its production environment policy, but the application revision can differ. Manual runs require `FLY_DEPLOY_ENABLED=true`; the selected revision must provide the production deployment Makefile target and configuration. The manual trigger becomes available after this workflow is present on the default branch.

Deployments are serialized without cancelling an active rollout. An automatic queued run skips an obsolete commit if a newer commit is already on `main`; an explicit manual deployment bypasses that check. Branches and tags resolve to a fixed commit at checkout, recorded in the workflow summary. Use a full commit SHA when the target must be fixed before the run starts. The build receives the resolved commit identifier, and the final health probe verifies that the public domain serves that commit. A failed final probe reports deployment failure; it does not automatically roll back. No separate release command or blue-green deployment is configured.

For rollback, prefer a reviewed revert on `main` through the same checks. The manual workflow rebuilds the selected source revision; it does not restore a previous image. An urgent manual rollback can instead use a previously verified image with current certificate stores; verify its build identifier and smoke test afterward. After any rollback or hotfix deployment, reconcile `main` or temporarily disable deployment: the next push to `main` can replace it.

## Preview deployment

The separate `web/fly.preview.toml` targets `reponomics-treestamp-preview`. Here, preview means a test deployment of the web editor. This app has been created but has not been deployed. Install its GitHub API credentials separately before its first deployment, using `make fly-secrets FLY_CONFIG=web/fly.preview.toml` if using a GitHub App. Preview deployment is manual and defaults to one Machine that may stop when idle:

```bash
make web-image
make fly-preview-deploy
make fly-status FLY_CONFIG=web/fly.preview.toml
```

Deploy a clean, committed candidate so that identifier describes the deployed files. The Docker build checks certificate stores; `make tls-check` performs the corresponding check in the local Python environment. Credentials belong in the host's secret store, not in Git.

After deploying, check `https://reponomics-treestamp-preview.fly.dev/healthz`, then run the public-repository smoke test with a matching local checkout:

```bash
make fly-smoke SMOKE_URL=https://reponomics-treestamp-preview.fly.dev \
    SMOKE_REPO=OWNER/REPOSITORY SMOKE_CHECKOUT=/path/to/checkout
```

The repository must be public, and the local checkout must contain the commit used by the hosted session. Verify loading, editing, copying, and draft preservation after failed loads in a browser. For rollback, redeploy a previously verified image with up-to-date certificate stores and recheck the build identifier and smoke test.

## Product page

The product information page and selected demos belong in the separate `reponomics-web` repository, using its static assets and website deployment. They are not deployed by this repository. Add the product-page link after that page is published.

## External setup checklist

- [ ] Configure `main` protections, required checks, signed commits, and immutable releases.
- [ ] Install the release App on this repository and configure its variable and secret.
- [ ] Finish the pending Trusted Publisher and review `pypi` environment protections; complete public review and enable publication before merging the first release PR.
- [ ] Enable private vulnerability reporting when the repository becomes public.
- [ ] Deploy the production configuration to `treestamp-preview` and verify two-Machine session routing and draft recovery.
- [x] Save the three Cloudflare DNS records without proxying and validate the Fly certificate.
- [ ] After the reviewed production deployment, enable Cloudflare proxying with Full (strict) TLS, verify cache behavior, and complete domain and smoke checks.
- [ ] Configure the `production` environment and app-scoped deploy token, then enable deployment from `main`.
- [ ] Configure credentials and deploy the new `reponomics-treestamp-preview` app before using it for previews.
- [ ] Publish the product page and demos from `reponomics-web` when ready.
