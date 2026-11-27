# Roadmap

## Proposed

- [ ] **Align annotations at specified column-number.**
- [ ] **Add protection against linters/formatters for filenames with trailing whitespace.**
- [ ] **Improve adoption flow by enabling direct writes from the TUI.** Instead of requiring the empty treestamp boundary markers, allow the user to insert a treestamp at a specified line.
- [ ] **Support additional SVG output styles.**

## Planned

- [ ] **Add dynamic testing.**

## In Progress

## Done

- [x] **Navigable note-transfer list in both editors.** Allow users to select notes in any order, revisit or remove transfers, ignore notes, and finish with explicit treatment of unresolved notes.
- [x] **Support SVG-based output formats.**

## Deferred/Dismissed

- [ ] **Automatically attempt annotation recovery across moves in the TUI.** Start with rename detection between `HEAD` and the captured index, then consider a bounded search of locally available history for unresolved annotated paths.
- [ ] **Investigate history-assisted annotation recovery in the web editor.** Explore GitHub blame information for annotated tree rows as a way to select candidate historical snapshots.
- [ ] **Define shared recovery confidence and feedback for both editors.**
- [ ] **Codefences optional for all display modes.**
