# Governance

Treestamp is owned by the [Reponomics](https://github.com/reponomics) GitHub organization and has one maintainer. One other member of the organization reviews pull requests.

## Members and access

| Member | Role | Access to sensitive resources |
| --- | --- | --- |
| [@hesreallyhim](https://github.com/hesreallyhim) | Maintainer | Repository and organization administration, repository secrets and environments, the Release Please GitHub App, the hosted editor's GitHub App, the PyPI project, the Fly.io apps, and the `reponomics.org` Cloudflare zone |

No other person has access to these resources.

## Roles and responsibilities

The maintainer:

- reviews and merges pull requests, and sets the project's direction and scope
- triages issues, discussions, and private vulnerability reports according to [SECURITY.md](../.github/SECURITY.md)
- approves releases by merging Release Please pull requests, and oversees PyPI publication and deployment of the hosted editor
- manages repository settings, rulesets, secrets, and credentials for the services listed above
- maintains the project's documentation, including this file

Reviewers are organization members with the Triage role. They review pull requests and help triage issues. Their reviews are advisory: merging does not require an approval. The Triage role cannot merge, push, run workflows, or create releases, and grants no access to the resources listed above.

Contributors propose changes through issues and pull requests, following [CONTRIBUTING](../.github/CONTRIBUTING.md) and the [code of conduct](../.github/CODE_OF_CONDUCT.md). Contributing does not grant write access or access to sensitive resources. Only the maintainer can merge; [CODEOWNERS](../.github/CODEOWNERS) records the maintainer as owner of all code.

## Decisions and changes to access

The maintainer makes project decisions, discussing significant changes in public issues or discussions before adopting them. Access to the resources above is granted only by the maintainer and is recorded in this file when it changes. Before anyone receives write access to the repository or access to these resources, the maintainer reviews their history of contributions to the project and approves the change. Access is limited to what the person's role requires.
