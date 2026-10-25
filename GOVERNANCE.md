# Governance

Treestamp is maintained by the Reponomics organization. It currently has one maintainer, who makes project decisions after discussion in public issues and pull requests.

## Members with access to sensitive resources

| Member | Access |
| --- | --- |
| [@hesreallyhim](https://github.com/hesreallyhim) | Owner of the `reponomics` GitHub organization and administrator of this repository, including rulesets, secrets, environments, and security advisories; owner of the `treestamp` PyPI project; the Release Please GitHub App and its private key; the Fly.io apps that host the web editor and their deploy tokens and GitHub credentials; DNS for `reponomics.org` in Cloudflare |

Other organization members and collaborators may have read access to the repository. Read access does not include settings, secrets, environments, publication, or deployment. This list is updated when someone gains or loses any of the access above.

## Roles and responsibilities

Maintainers review and merge pull requests, triage issues and discussions, respond to vulnerability reports under the [security policy](.github/SECURITY.md), publish releases, operate the hosted editor, and manage the project's dependencies, credentials, and repository settings as described in [MAINTENANCE.md](MAINTENANCE.md). They keep this file, the security policy, and the contributor guide current.

Contributors propose changes through issues and pull requests, following the [contributor guide](.github/CONTRIBUTING.md) and the [code of conduct](.github/CODE_OF_CONDUCT.md). Pull requests from anyone must pass the required checks before a maintainer merges them.

Automated accounts act only within the permissions given to them: Release Please opens release pull requests and creates tags and releases after a maintainer merges a release pull request, Dependabot proposes dependency updates as pull requests, and GitHub Actions workflows build, test, publish, and deploy as configured in [`.github/workflows`](.github/workflows).
