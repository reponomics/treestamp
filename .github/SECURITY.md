# Security reporting

Report suspected vulnerabilities through [GitHub private vulnerability reporting for reponomics/treestamp](https://github.com/reponomics/treestamp/security/advisories/new). Do not post sensitive vulnerability details in public issues.

Include the affected version or hosted build commit, the command or request, the impact, and a minimal reproduction. Remove credentials and unrelated private data from examples. Use [public issues](https://github.com/reponomics/treestamp/issues) for ordinary bugs and [conduct@reponomics.org](mailto:conduct@reponomics.org) for conduct reports.

Repository snapshots are cached temporarily. See [PRIVACY.md](../PRIVACY.md) for the service's privacy notice.

## Coordinated disclosure

The maintainers acknowledge each private report within 14 days and keep the discussion in the private advisory. After confirming a vulnerability, they prepare a fix in a private fork or branch, agree on a disclosure date with the reporter, and aim to publish within 90 days of the report. A fix for the hosted editor may be deployed before the advisory is published. If a report is not accepted as a vulnerability, the maintainers explain why in the advisory.

Confirmed vulnerabilities are published as [GitHub security advisories](https://github.com/reponomics/treestamp/security/advisories), which list the affected and fixed versions, how to tell whether an installation is affected, and how to upgrade or otherwise mitigate the issue. The release notes for the fixed version reference the advisory. Reporters are credited unless they ask not to be.

## Supported versions

Security fixes are made in the latest release; upgrade to that release to receive them. Older versions are not maintained separately. The hosted editor at <https://treestamp.reponomics.org> always runs a recent `main` revision and needs no action from users.
