# Use minimal historical decision records

Status: accepted.

## Context and Problem Statement

Existing ADRs have accumulated detailed specifications, implementation plans, and results. Treating those records as ongoing references duplicates durable documentation and makes historical decisions appear binding on future product changes.

## Considered Options

- Continue expanding existing ADRs as living specifications.
- Adopt MADR's minimal template for short historical records and maintain current requirements separately.

## Decision Outcome

Chosen option: minimal historical records, because decisions need a concise explanation without becoming a second source of current requirements. Future ADRs use the copied [minimal template](adr-template-minimal.md), with a status line, following the [directory guidance](README.md). Existing records need not be rewritten. Changed decisions receive a superseding record. Durable documents normally avoid ADR references, except where historical context is useful.

### Consequences

- Decision history remains available without prescribing current behavior.
- Authors must maintain current requirements in the relevant durable documentation rather than relying on an ADR.
