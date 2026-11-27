# Architecture decision records

ADRs are short historical records of consequential decisions and their tradeoffs. They are not durable reference material, specifications, implementation plans, or test reports. Current behavior and requirements belong in the relevant design, testing, or user documentation.

For future records, copy [MADR's minimal template](adr-template-minimal.md), choose the next four-digit number and a descriptive filename, and add a `Status: proposed`, `Status: accepted`, or `Status: superseded` line below the title. Aim for a few concise paragraphs, usually one page. Earlier records are more verbose; they are historical examples, not the standard for new records.

When a decision changes, write a new record and mark the previous one superseded with a link. Keep its historical reasoning rather than rewriting it into current guidance. ADRs may refer to other ADRs. Durable documentation should usually stand on its own; an occasional ADR link is appropriate only for useful historical context, never as the authority for current behavior.

The included template is copied from [MADR](https://github.com/adr/madr/blob/develop/template/adr-template-minimal.md). Its upstream formatting is retained; see [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) for attribution and licensing.

Optional reading, when available: Martin Fowler's [Architecture Decision Record](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html). Access to this article is not a prerequisite for contributing or authoring an ADR.
