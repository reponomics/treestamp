# Security assessment

This assessment identifies the security problems most likely to occur in treestamp, or most harmful if they did, and the measures that address them. It covers the current source, including changes since release 0.1.2, and the hosted editor deployed from `main`, using the actors and interfaces in the [design document](design.md). Revise it when a change adds an interface, an actor, a credential, or a new kind of stored or transmitted data.

Last reviewed: 2026-10-28.

## Assets and trust boundaries

- **Users' documents and checkouts.** The CLI and terminal editor read a local Git repository and may replace one Markdown document in it.
- **Hosted-service credentials.** The private key of the GitHub App the hosted service uses to obtain installation tokens, held in Fly.io secrets.
- **Release credentials.** The Release Please App key, the PyPI Trusted Publishing identity, and the Fly.io deploy token, held in GitHub secrets and environments.
- **Service availability and GitHub request budget.** Shared by all visitors of the hosted editor.

Untrusted input crosses these boundaries: repository contents (file names, symlink targets, and documents) for both editors; repository links, request bodies, and state envelopes from web visitors; and pull requests from contributors.

## Attack surface

These are the points where untrusted or externally controlled input enters the system, and the code that handles it first. The threat tables below are organized around them.

| Entry point | Input | First handled by |
| --- | --- | --- |
| [Hosted HTTP API](design.md#hosted-http-api) | Repository links, query parameters, JSON bodies, state envelopes, operation paths, and annotation text | `app.py` (body size and rate limits), `links.py`, `preview.py` |
| GitHub API responses | Metadata, tree listings, symlink targets, and documents from public repositories | `github.py` (response size and time limits), `sources.py`, `document.py`, `codec.py` |
| Proxy and routing headers | `CF-Connecting-IP`, Fly.io replay headers, and the session-affinity cookie | `proxy.py`, `routing.py` |
| [Command line](design.md#command-line) | Arguments, document paths, and Git refs | `cli.py`, `gitio.py` |
| Local repositories | File names, symlink targets, and documents in the checkout; the repository's Git configuration and the `git` on `PATH` | `gitio.py`, `document.py`, `codec.py` |
| Contributions | Pull requests, PR titles, and issues processed by CI | Pull-request workflows, which run with read-only tokens |
| Manually triggered workflows | `workflow_dispatch` inputs: the deployment revision and the README update's base branch | `deploy.yml`, `treestamp-update.yml` |
| Dependencies and actions | Third-party packages, the container base image, and GitHub Actions | `uv.lock`, the pinned image digest, and pinned action SHAs |

The critical code paths are repository-link parsing in `links.py`, the public-visibility check in `github.py`, document and row parsing in `document.py` and `codec.py`, and the document write path in `document.py`.

## Hosted editor

| Threat | Risk context and potential impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| Request forgery to hosts other than GitHub, through a crafted repository link | Accepts public input; impact would depend on which unintended destinations could be reached | `links.py` is the only path from user text to a GitHub request. Owner and repository names are validated against GitHub's character rules and URL-quoted; the API base URL is fixed configuration | None identified |
| Reading a private repository through the service's GitHub credentials | Fetching private data would require the credential to have access; previously public data can remain cached | Only public repositories are acquired, and only at their default-branch HEAD; a pinned commit is served only from a snapshot acquired that way (see [hosted actions](design.md#hosted-actions)) | A repository made private after acquisition stays readable from the cache until the snapshot expires (at most one hour) |
| Script injection through file names, annotations, or document text shown in the browser | Successful injection could read or alter the visitor's current editor content | The browser application inserts untrusted text without HTML parsing (no `innerHTML`). `Content-Security-Policy: default-src 'self'` blocks inline and third-party scripts. `nosniff` and `no-referrer` headers are set on every response | A future frontend change could introduce an HTML sink; the CSP limits the effect |
| Resource exhaustion or exhaustion of the GitHub request budget | Public requests consume shared resources; exhaustion can temporarily interrupt repository loading or editing | Per-client rate limits on loads and operations; request bodies capped before buffering; GitHub responses capped by size and time; documents capped at 1 MiB; at most 100 special-path registrations per document, rejected before identity resolution when exceeded; bounded identity-search branching; truncated or oversized tree listings refused; a symlink-fetch limit per subtree; a reserved share of the GitHub budget | Limits are per process; a distributed client can still consume the budget. GitHub quota exhaustion leaves editing available while its snapshot remains cached; cache eviction or service failure can interrupt editing |
| Spoofed client addresses to evade rate limits | Could bypass per-client limits and contribute to resource exhaustion | `CF-Connecting-IP` is accepted only when the connecting peer is in the configured Cloudflare ranges; otherwise the peer address is used | Depends on keeping the Cloudflare range list current |
| Tampered state envelope | Visitors control their submitted state; changes affect their own rendered result | The service validates the envelope's structure and requires its source to match the request's repository, commit, root, and document. The envelope grants no access beyond the snapshot named in the request | A visitor can only alter their own result |
| Disclosure of visitor data | Request logs can reveal which repositories or documents a visitor requested | Application structured logs omit document contents and client addresses (see [hosted actions](design.md#hosted-actions) and [PRIVACY.md](../PRIVACY.md)) | Uvicorn access logging is enabled by default and includes a client address and request path/query; hosting providers may also retain request logs |

## Command line and terminal editor

| Threat | Risk context and potential impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| Option or command injection through refs and paths passed to Git | Unlikely; high impact | Git runs with an argument list, never a shell, with a timeout and a limit on collected output. User-supplied refs are resolved with `rev-parse --verify --end-of-options`; later commands receive only object ids. `diff` runs with `--no-ext-diff` and `--no-textconv` | treestamp runs the `git` found on `PATH` and inherits the repository's Git configuration |
| Writing outside the repository or through a symlink | Unlikely; high impact (loss of user data) | Document paths outside the repository, through symlinks, or into submodules are refused, as the [README](../README.md) documents | None identified |
| Overwriting concurrent edits or leaving a partial file | Concurrent edits can occur in normal use; losing an edit has medium impact | Writes are refused if the document changed after it was read, and replace it atomically (see [local actions](design.md#local-actions)) | A change made between the final check and the replace can still be lost |
| Terminal or Markdown injection through file names in a repository | Third-party repositories can supply crafted names; misleading or injected output has medium impact | Control characters and unsafe bytes are escaped in output; fenced styles prefix every row so a name cannot close the fence; list-style output escapes Markdown. Rendered output is parsed back and must reproduce the tree, or it is refused | Bidirectional formatting characters in names are not escaped and can make a row display misleadingly |

## Supply chain and release

| Threat | Risk context and potential impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| A compromised or vulnerable dependency | Dependencies can acquire vulnerabilities over time; exploitation or malicious code can have high impact | Few runtime dependencies, selected, locked, and tracked as described in [CONTRIBUTING](../.github/CONTRIBUTING.md#dependencies); [OSV-Scanner](../.github/workflows/osv-scanner.yml) checks locked dependency versions for known vulnerabilities | A malicious release of a dependency can be adopted if a review misses it |
| Malicious code in a pull request reaching credentials | Contributor code runs in CI; credential exposure could compromise releases or deployment | PR workflows run with read-only tokens and no secrets; the only `pull_request_target` workflow does not check out PR code. Actions are pinned to commit SHAs. `main` accepts changes only through pull requests with passing required checks | The project has one maintainer, so review is not independent of authorship for maintainer changes |
| Publishing a tampered or unintended package | Unlikely; high impact | The [release process](./MAINTENANCE.md#repository-and-release-setup) validates and builds each release from source and publishes it through PyPI Trusted Publishing with attestations, without long-lived tokens; releases are immutable | Compromise of the maintainer's GitHub account would bypass these controls; the organization requires two-factor authentication |
| Leaked deployment or service credentials | Unlikely; high impact | Credentials are scoped to one app or repository and stored as [MAINTENANCE.md](./MAINTENANCE.md#repository-and-release-setup) describes; secret scanning with push protection is enabled; `/healthz` reports the credential type, never its value | Credential rotation depends on the maintainer |

## Follow-up

- Recheck this assessment when the hosted editor gains new operations or persistence, or when the CLI gains network access.
- Report suspected vulnerabilities as described in [SECURITY.md](../.github/SECURITY.md).
