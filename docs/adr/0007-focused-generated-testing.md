# Begin generated testing at shared document and parsing boundaries

Status: accepted. Supersedes [ADR 0003](0003-dynamic-testing-plan.md).

## Context and Problem Statement

The initial generated-testing implementation combines shared document checks with browser-worker infrastructure and assertions about tentative hosted cache mechanics. Treestamp's primary journey is maintaining documentation stored and rendered on GitHub; tests should protect that journey without turning implementation details into product requirements.

## Considered Options

- Adopt the full generated service, cache, and browser apparatus immediately.
- Begin with document properties, core session transport, and hosted request parsing, retaining focused regressions for discovered defects.

## Decision Outcome

Chosen option: the narrower initial scope, because it delivers independent semantic checks with less infrastructure and policy coupling. Property tests live under each suite's `tests/properties/` directory and run in ordinary CI. Defer the Python-to-Node worker, broad service/cache mutation apparatus, and separate browser injection corpus; retain product fixes and ordinary targeted regressions.

Current requirements belong in durable design and testing documentation. Tests of current format limitations must change when the supported format changes. Core transport tests establish fidelity within the implementation, not persistence or cross-version session compatibility. Cache retention, resumption, and state-bearing URLs create no public persistence or sharing promise.

Both editors share document semantics. Acquisition and resource limits may differ, but a browser display or response-encoding limitation must not alone prevent processing a valid document. Shared preparation regenerates configuration from its validated values when retaining its original text would prevent UTF-8 output; this exceptional normalization may discard config comments but preserves semantic values and surrounding Markdown bytes. Ordinary supported formatting remains preserved. Targeted interoperability regressions cover this change without a whole-system redesign.

### Consequences

- Generated tests protect document identity, curation, preservation, transport, and controlled request parsing with a smaller maintenance burden.
- Broader generated browser and service exploration is deferred. Existing deterministic coverage remains, and newly discovered defects retain focused regression tests.
- Changing product behavior includes updating the relevant expectations and documentation; tests and historical decisions do not veto that change.
