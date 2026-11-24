# ADR 0001: Coherence of CLI paths and repository selection

- Status: Accepted and implemented
- Date: 2026-10-29
- Decision updated: 2026-11-24
- Scope: CLI paths, editor startup, extraction, and unattended maintenance

## Context

Treestamp distinguishes the Git repository, the subtree being documented, and the document containing the treestamp. Shell paths must follow the caller's current working directory, while stored paths need a stable identity independent of that directory. A first-time user should reach the editor immediately; returning users should be able to load the README beside their current work without navigating a second filesystem browser.

The previous startup chooser displayed working-tree files, including ignored and untracked entries, although the resulting tree used the staged Git index. This introduced an extra decision and an inaccurate impression of the source. The previous repository-root README default also made implicit paths behave differently from explicit paths when invoked in a subdirectory.

## Decision

### Direct entry and paths

The public editor commands are `new [PATH]` and `load [DOCUMENT]`. They replace the `tui` command and `--load` flag. Both open the editor directly; the terminal source picker and New/Load screen are removed. The web source picker is unaffected.

Bare `treestamp` inspects `README.md` in cwd. A valid treestamp loads an updated interactive draft. A missing README or one without a treestamp starts a new draft rooted at cwd. An unreadable document, malformed markers, or invalid treestamp is an error; automatic creation is not a recovery strategy for failed loads. Bare invocation outside Git fails.

`new` always starts a fresh draft, even if a README already contains a treestamp. Its default root is cwd. An explicit existing directory becomes the root; an explicit regular file selects its parent directory. A nonexistent path fails. Selecting a file for `new` does not load it or attach it as a write destination. New drafts are exported by copying or printing.

`load`, `check`, and `update` default to cwd's `README.md` and require a valid treestamp. Explicit paths are cwd-relative or absolute and select their containing repository, including when cwd is outside Git. Loading respects the document's saved repository-relative root: the location of the document does not redefine the tree it describes.

CLI discovery rejects symlinks before normalizing parent components. An initialized nested repository or submodule can own an explicitly selected source; an uninitialized submodule remains a boundary. Editor-session paths and stored configuration remain repository-relative; rendered entries remain relative to the selected tree root. For example, `new .` from `docs/` selects that directory and records root `docs`, not repository root `.`.

### Extraction and generation

`load [DOCUMENT] --print` validates and extracts the stored treestamp region, preserving its supported bytes, markers, metadata, and formatting. It does not acquire a current Git snapshot, apply updates, or inspect unmatched notes. Staleness is irrelevant to extraction. Repository/path validation and document validity still apply. The existing terminal-control display protection remains in effect for direct terminal output; redirected output preserves the extracted bytes.

`new [PATH] --print` generates a new treestamp from the selected root's staged Git index. Bare `--print` follows automatic source selection: extract a valid treestamp from cwd's README, or generate a fresh tree at cwd when the README is missing or unmarked. Malformed documents fail. Printing never writes a document and accepts no update or note-transfer flags. An explicit `update` followed by `load --print` prints the updated saved document.

### Updates and unmatched notes

Interactive loading prepares an updated draft from the staged index. Only unmatched notes trigger the existing transfer-choice modal. The queue-based transfer view retains Transfer, Skip, and Undo; a navigable list remains deferred for both interfaces. No document is changed until the user chooses Write.

`update` prepares automatic changes, including supported rename matching requested through `--compare`. If notes would still be omitted, it fails before writing. The diagnostic identifies the need to transfer notes interactively or explicitly accept their omission with `--skip-notes-transfer`. The override permits dropping only unmatched notes; matched and successfully moved notes remain preserved. Notes on kind-changed paths, conflicting move destinations, or destinations omitted from the resulting draft must not evade this check merely because a destination path exists.

`check` computes the proposed replacement and remains read-only. It reports drift and any notes that the automatic replacement would omit, without opening a transfer view. Both maintenance commands retain explicit `--target` and `--compare` support. Their snapshots and comparisons belong to the selected document's repository.

## Alternatives considered

| Option | Assessment |
| --- | --- |
| Always open a source picker | Adds friction and exposes filesystem contents that differ from the Git source; removed |
| Default implicit loads to repository root | Convenient for repository-wide checks, but inconsistent with explicit relative paths and subtree workflows; replaced by cwd |
| Treat every failed automatic load as a new draft | Masks malformed or unreadable existing work; rejected |
| Refresh the draft during `load --print` | Prints something different from the document and introduces unattended note-loss decisions; replaced by extraction |
| Silently drop unmatched notes during `update` | Can remove authored content without acknowledgement; replaced by an explicit override |
| Replace the transfer queue with a navigable list now | Useful follow-up, but independent of startup and maintenance semantics; deferred |

## Consequences

This is an intentional CLI compatibility change. Scripts using `tui`, `--load`, repository-root implicit paths from subdirectories, automatic refresh through printing, or unconditional updates that remove notes must adopt the new semantics. The [CLI reference](../cli-reference.md) is the source of syntax and usage examples.

The staged Git index remains the source for new trees and automatic updates. Empty or incomplete staged trees need clear feedback rather than silently incorporating untracked files. Document serialization and the web editor's startup and transfer interactions are unchanged.

Regression coverage must distinguish source selection from saved tree scope, automatic fallback from load failures, extraction from snapshot-dependent updates, and matching notes from omitted notes after rename handling. Existing filesystem boundaries, transactional writing, and terminal-output protections remain required.
