# Roadmap

This document defines some of the features, enhancements, and bug-fixes that are currently tracked by the project's maintainer and contributors. It is not currently organized into a specific timeline and no guarantees regarding delivery can be made at this time.

## Implemented CLI contract

The CLI decisions discussed on 2026-10-29 and 2026-10-30 are implemented for the next release; see [ADR 0001: Coherence of CLI paths and repository selection](adr/0001-cli-path-coherence.md).

- [x] **Resolve explicit CLI document paths relative to cwd.** `--load DOCUMENT`, `check DOCUMENT`, and `update DOCUMENT` accept relative or absolute paths and infer the document's repository. Omitted headless document arguments retain the repository-root README default; editor and stored paths remain repository-relative.
- [x] **Replace `--document` with `--load`.** Explicit loads open directly, bypassing the opening choice and path-entry dialog. Without `--load`, use cwd's repository and retain New/Load. `--print` retains its existing default README fallback; no compatibility alias is provided.
- [x] **Remove positional repository `PATH`.** Use the explicitly loaded document's repository, otherwise cwd's repository, without a replacement repository option. `--target` and `--compare` keep their existing meanings in the selected repository.

## Ideas awaiting decisions or implementation

The following feature proposals remain outside the CLI contract and do not block 1.0.

- [ ] **Automatically attempt annotation recovery across moves in the TUI.** Start with rename detection between `HEAD` and the captured index, then consider a bounded search of locally available history for unresolved annotated paths. Bound execution time and history depth, use the captured target consistently, and allow editing to continue when evidence is unavailable. Today, move-based annotation transfer requires an explicit `--compare` on CLI `check` or `update`.
- [ ] **Investigate history-assisted annotation recovery in the web editor.** Explore GitHub blame information for annotated tree rows as a way to select candidate historical snapshots, then verify old-path existence and rename evidence against the captured target. Blame identifies each line's last change, not a guaranteed generation commit for the whole tree; different rows may need different candidates. Evaluate API support, caching, request budgets, and graceful fallback before implementing this approach.
- [ ] **Define shared recovery confidence and feedback for both editors.** Keep transfers conservative when paths have been reused, copied, or renamed multiple times; conflicting candidate histories should not silently select an annotation destination. Preserve existing destination annotations and respect subtree scope, hidden entries, and collapsed directories. Report successful transfers and annotated paths that could not be matched, rather than silently dropping unresolved notes from the updated draft.
