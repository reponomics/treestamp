# Security assessment

This assessment identifies the security problems most likely to occur in Treestamp, or most harmful if they did, and the measures that address them. It covers release 0.1.1 and the hosted editor deployed from `main`, using the actors and interfaces in the [design document](design.md). Revise it when a change adds an interface, an actor, a credential, or a new kind of stored or transmitted data.

Last reviewed: 2026-10-28.

## Assets and trust boundaries

- **Users' documents and checkouts.** The CLI and terminal editor read a local Git repository and may replace one Markdown document in it.
- **Hosted-service credentials.** The GitHub token or GitHub App private key used by the hosted service, held in Fly.io secrets.
- **Release credentials.** The Release Please App key, the PyPI Trusted Publishing identity, and the Fly.io deploy token, held in GitHub secrets and environments.
- **Service availability and GitHub request budget.** Shared by all visitors of the hosted editor.

Untrusted input crosses these boundaries: repository contents (file names, symlink targets, and documents) for both editors; repository links, request bodies, and state envelopes from web visitors; and pull requests from contributors.

## Hosted editor

| Threat | Likelihood and impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| Request forgery to hosts other than GitHub, through a crafted repository link | Likely to be attempted; high impact if it succeeded | `links.py` is the only path from user text to a GitHub request. Owner and repository names are validated against GitHub's character rules and URL-quoted; the API base URL is fixed configuration | None identified |
| Reading a private repository through the service's GitHub credentials | Likely to be attempted; high impact | Only public repositories are acquired, and only at their default-branch HEAD; a pinned commit is served only from a snapshot acquired that way (see [hosted actions](design.md#hosted-actions)) | A repository made private after acquisition stays readable from the cache until the snapshot expires (at most one hour) |
| Script injection through file names, annotations, or document text shown in the browser | Likely to be attempted; high impact | The browser application inserts untrusted text without HTML parsing (no `innerHTML`). `Content-Security-Policy: default-src 'self'` blocks inline and third-party scripts. `nosniff` and `no-referrer` headers are set on every response | A future frontend change could introduce an HTML sink; the CSP limits the effect |
| Resource exhaustion or exhaustion of the GitHub request budget | Likely; medium impact (loss of availability for all visitors) | Per-client rate limits on loads and operations; request bodies capped before buffering; GitHub responses capped by size and time; truncated or oversized tree listings refused; a symlink-fetch limit per subtree; a reserved share of the GitHub budget | Limits are per process; a distributed client can still consume the budget. Exhaustion stops new loads but not existing sessions |
| Spoofed client addresses to evade rate limits | Likely to be attempted; low impact | `CF-Connecting-IP` is accepted only when the connecting peer is in the configured Cloudflare ranges; otherwise the peer address is used | Depends on keeping the Cloudflare range list current |
| Tampered state envelope | Likely to be attempted; low impact | The service validates the envelope's structure and requires its source to match the request's repository, commit, root, and document. The envelope grants no access beyond the snapshot named in the request | A visitor can only alter their own result |
| Disclosure of visitor data | Unlikely; medium impact | Logs omit document contents and client addresses (see [hosted actions](design.md#hosted-actions) and [PRIVACY.md](../PRIVACY.md)) | Fly.io and Cloudflare keep their own request logs |

## Command line and terminal editor

| Threat | Likelihood and impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| Option or command injection through refs and paths passed to Git | Unlikely; high impact | Git runs with an argument list, never a shell, with a timeout and an output size limit. User-supplied refs are resolved with `rev-parse --verify --end-of-options`; later commands receive only object ids. `diff` runs with `--no-ext-diff` and `--no-textconv` | Treestamp runs the `git` found on `PATH` and inherits the repository's Git configuration |
| Writing outside the repository or through a symlink | Unlikely; high impact (loss of user data) | Document paths outside the repository, through symlinks, or into submodules are refused, as the [README](../README.md) documents | None identified |
| Overwriting concurrent edits or leaving a partial file | Likely in normal use; medium impact | Writes are refused if the document changed after it was read, and replace it atomically (see [local actions](design.md#local-actions)) | A change made between the final check and the replace can still be lost |
| Terminal or Markdown injection through file names in a repository | Likely when documenting third-party repositories; medium impact | Control characters and unsafe bytes are escaped in output; fenced styles prefix every row so a name cannot close the fence; list-style output escapes Markdown. Rendered output is parsed back and must reproduce the tree, or it is refused | Bidirectional formatting characters in names are not escaped and can make a row display misleadingly |

## Supply chain and release

| Threat | Likelihood and impact | Measures | Remaining risk |
| --- | --- | --- | --- |
| A compromised or vulnerable dependency | Likely over time; high impact | Few runtime dependencies, selected, locked, and tracked as described in [CONTRIBUTING](../.github/CONTRIBUTING.md#dependencies); CodeQL scanning (see [MAINTENANCE.md](../MAINTENANCE.md#repository-and-release-setup)) | A malicious release of a dependency can be adopted if a review misses it |
| Malicious code in a pull request reaching credentials | Likely to be attempted; high impact | PR workflows run with read-only tokens and no secrets; the only `pull_request_target` workflow does not check out PR code. Actions are pinned to commit SHAs. `main` accepts changes only through pull requests with passing required checks | The project has one maintainer, so review is not independent of authorship for maintainer changes |
| Publishing a tampered or unintended package | Unlikely; high impact | The [release process](../MAINTENANCE.md#repository-and-release-setup) validates and builds each release from source and publishes it through PyPI Trusted Publishing with attestations, without long-lived tokens; releases are immutable | Compromise of the maintainer's GitHub account would bypass these controls; the organization requires two-factor authentication |
| Leaked deployment or service credentials | Unlikely; high impact | Credentials are scoped to one app or repository and stored as [MAINTENANCE.md](../MAINTENANCE.md#repository-and-release-setup) describes; secret scanning with push protection is enabled; `/healthz` reports the credential type, never its value | Credential rotation depends on the maintainer |

## Follow-up

- Recheck this assessment when the hosted editor gains new operations or persistence, or when the CLI gains network access.
- Report suspected vulnerabilities as described in [SECURITY.md](../.github/SECURITY.md).
