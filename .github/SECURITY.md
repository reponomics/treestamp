# Security reporting

Report suspected vulnerabilities through [GitHub private vulnerability reporting for reponomics/treestamp](https://github.com/reponomics/treestamp/security/advisories/new). Do not post sensitive vulnerability details in public issues.

Include the affected version or hosted build commit, the command or request, the impact, and a minimal reproduction. Remove credentials and unrelated private data from examples. Use [public issues](https://github.com/reponomics/treestamp/issues) for ordinary bugs and [conduct@reponomics.org](mailto:conduct@reponomics.org) for conduct reports.

## Coordinated disclosure

The maintainer acknowledges each report within 14 days and keeps the reporter informed while it is assessed and fixed. The project aims to release a fix and publish the vulnerability within 90 days of the report, and coordinates the publication date with the reporter. Earlier publication may be necessary if the vulnerability is already public or actively exploited.

Confirmed vulnerabilities are published as [GitHub security advisories](https://github.com/reponomics/treestamp/security/advisories), with the affected and fixed versions, how to tell whether a system is affected, and how to remediate it. A CVE is requested through GitHub when appropriate, and the fix appears in the [changelog](../CHANGELOG.md).

## Dependency and code scanning findings

OSV-Scanner and Dependabot report known vulnerabilities in dependencies, and CodeQL reports security weaknesses in the code. Findings are fixed according to their severity, counted from when they are reported:

| Severity | Fixed |
| --- | --- |
| Critical or high | Before the next release, and within 30 days |
| Medium | Within 90 days |
| Low | At the maintainer's discretion |

Dependencies must meet the license requirement in [CONTRIBUTING](CONTRIBUTING.md#dependencies); a dependency that does not is replaced or removed before the next release. No release is published while a critical or high finding or a license violation is open. A finding that does not affect treestamp may be suppressed only with a recorded reason, given in the code scanning dismissal or the scanner's ignore entry.

## Supported versions

Each release is supported until the next release is published. Support covers bug fixes and security fixes, which are delivered in a new release; once a newer release exists, earlier releases receive no further updates, including security updates. The project does not provide long-term support for older versions. The hosted editor runs the current `main` and receives fixes when it is redeployed. Reports should identify the exact affected version.

Repository snapshots are cached temporarily. See [PRIVACY.md](../PRIVACY.md) for the service's privacy notice.
