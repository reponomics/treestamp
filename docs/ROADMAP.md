# Roadmap

This document defines some of the features, enhancements, and bug-fixes that are currently tracked by the project's maintainer and contributors. It is not currently organized into a specific timeline and no guarantees regarding delivery can be made at this time.

## Ideas awaiting decisions or implementation

These feature proposals are not prerequisites for 1.0.

- [ ] **Automatically attempt annotation recovery across moves in the TUI.** Start with rename detection between `HEAD` and the captured index, then consider a bounded search of locally available history for unresolved annotated paths. Bound execution time and history depth, use the captured target consistently, and allow editing to continue when evidence is unavailable. Today, move-based annotation transfer requires an explicit `--compare` on CLI `check` or `update`.
- [ ] **Investigate history-assisted annotation recovery in the web editor.** Explore GitHub blame information for annotated tree rows as a way to select candidate historical snapshots, then verify old-path existence and rename evidence against the captured target. Blame identifies each line's last change, not a guaranteed generation commit for the whole tree; different rows may need different candidates. Evaluate API support, caching, request budgets, and graceful fallback before implementing this approach.
- [ ] **Define shared recovery confidence and feedback for both editors.** Keep transfers conservative when paths have been reused, copied, or renamed multiple times; conflicting candidate histories should not silently select an annotation destination. Preserve existing destination annotations and respect subtree scope, hidden entries, and collapsed directories. Report successful transfers and annotated paths that could not be matched, rather than silently dropping unresolved notes from the updated draft.
- [ ] **Codefences optional for all display modes.**
- [ ] **Align annotations at specified column-number.**
