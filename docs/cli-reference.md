# CLI reference

This reference describes the current CLI. [ADR 0001](adr/0001-cli-path-coherence.md) records the accepted path-handling and repository-selection contract. See [Design](design.md) for the document format and architecture.

## Commands

```text
treestamp [tui] [--load DOCUMENT] [--print]
treestamp check [DOCUMENT] [--target REF] [--compare REF]
treestamp update [DOCUMENT] [--target REF] [--compare REF]
treestamp --version
treestamp --help
```

With no command, `treestamp` opens the TUI. `tui` can also be omitted before its options: `treestamp --print` and `treestamp tui --print` are equivalent. Use `treestamp tui --help`, `treestamp check --help`, or `treestamp update --help` for command-specific help.

## Repositories, paths, and snapshots

| Input | Interpretation |
| --- | --- |
| `--load DOCUMENT` | A cwd-relative or absolute document path; opens it directly and selects its containing repository |
| Explicit `check DOCUMENT` / `update DOCUMENT` | A cwd-relative or absolute document path; selects its containing repository |
| Omitted document for `check`, `update`, or `--print` | The repository-root `README.md` in the repository containing cwd |
| TUI startup without `--load` | The repository containing cwd; shows New/Load |
| TUI tree root and document dialogs | Paths relative to the selected repository root |

Explicit CLI document paths follow filesystem conventions. From `docs/`, `treestamp check README.md` checks `docs/README.md`, while `treestamp check ../README.md` checks the repository's top-level README. Bare `treestamp check` still selects the top-level README. A document can select another checkout even when cwd is outside any repository.

CLI document paths may include `..`, but symlinks are refused, including traversed components before parent normalization. A document in an initialized nested repository or submodule selects that repository. Paths into an uninitialized submodule are rejected. Within the editor, document paths remain repository-root-relative: absolute paths, parent traversal, symlinks, and crossings into other repositories or submodules are rejected.

There is no positional repository argument. To open another repository, load a document in it or change directories before starting treestamp. Choose a subtree in the New document dialog; the root dialog accepts spellings such as `./src/` and stores the canonical `src` path.

The default source is a captured Git index, not the working tree. Stage additions, deletions, and renames before opening or checking a treestamp. Untracked files are absent, and unstaged changes are not incorporated. New or Load captures a snapshot; subsequent edits use that snapshot until another New or Load operation. The containing document is read from disk, not from the index. Treestamp does not stage or commit files or fetch remote history.

## Interactive editor

```bash
treestamp
treestamp --load docs/structure.md
treestamp tui --load /path/to/another/checkout/README.md
```

Without `--load`, startup offers **New document** or **Load document**. `--load DOCUMENT` opens the document directly, bypassing the opening choice and path-entry dialog. An invalid explicit load reports an error without launching the editor or starting a new document. New document starts with the selected root's immediate children and collapsed directories. Load reads a valid existing treestamp and updates its draft against the captured index while preserving supported curation.

| Keys | Action |
| --- | --- |
| Arrow keys, Space, Home/End, Page Up/Down | Navigate and expand or collapse directories |
| `h`, `H`, `S` | Hide/unhide an entry, reveal hidden entries for browsing, unhide all |
| `a` | Edit the selected entry's annotation |
| `c`, `s`, `t` | Toggle counts, cycle Unicode/ASCII/list style, toggle attribution footer |
| `N`, `l` | Start a new document or load an existing one |
| `n`, `w` | Write a new file or replace the treestamp in an existing file |
| `v`, `y`, `p` | Preview, copy the complete treestamp, print it and exit |
| `?`, `q` / Escape | Help, quit |

Write new file requires a nonexistent destination. Write to existing requires a boundary-marker pair and preserves content outside it. Empty markers are valid as a write destination, but cannot be loaded as a tree: start with New document, then Write to existing. Copy includes markers and any configuration comment. Unwritten changes require confirmation before quitting or replacing the draft.

## Print without opening the editor

```bash
treestamp --print
treestamp --load docs/structure.md --print
```

`--print` writes the complete treestamp to stdout without changing a document. With explicit `--load`, the file must contain a valid treestamp; its updated draft is printed. Without `--load`, a valid treestamp in the repository-root README is loaded, while an absent README or one without markers starts a new tree. Malformed or empty marked regions are errors, not requests to initialize a tree.

Printing does not accept `--target` or `--compare`. Shell redirection writes independently of treestamp; do not redirect output over a document the command must read.

## Check and update

```bash
treestamp check
treestamp check docs/structure.md --target HEAD
treestamp update docs/structure.md --compare HEAD
treestamp check README.md --target HEAD --compare HEAD~1
```

Both commands require an existing, valid treestamp. `check` computes the same replacement as `update` without writing it. It prints `Current: …` and exits `0` when unchanged, or a unified diff and exits `1` when an update would change the document, including generated formatting. `update` replaces only the managed region, preserves surrounding bytes and line endings, and prints `Updated: …` or `Current: …`.

`--target REF` selects a local Git revision in the document's repository instead of its captured index. `--compare REF` supplies the earlier revision for Git rename detection. For example, `--compare HEAD` can preserve annotations across staged renames; after committing a rename, select an appropriate earlier comparison revision.

Annotation transfer is best effort: supported moves must remain within the selected subtree, destination annotations take precedence, and hiding and collapse choices are respected. Directory annotations are not transferred by rename detection. Without `--compare`, annotations are preserved at unchanged paths but do not follow moves. TUI loading and `--print` do not perform rename detection.

## Migrating from 0.3.x

`--document` has been removed without a compatibility alias. Use `--load DOCUMENT`, which now opens the document directly. The positional repository `PATH` has also been removed; replace `treestamp /other/project --document README.md` with `treestamp --load /other/project/README.md`, or change directories and run `treestamp` to retain the New/Load choice.

Explicit document paths now resolve from cwd instead of the repository root. From a repository's `docs/` directory, replace `treestamp check README.md` with `treestamp check ../README.md` to continue checking the root README, or omit the document argument. Apply the same adjustment to `update` and `--load`. Stored treestamps and paths entered within the editor do not need migration.

## Output and exit status

Printed output uses UTF-8 and LF line endings. Writing into an existing document preserves its line-ending convention. Diagnostic errors go to stderr.

| Exit status | Meaning |
| --- | --- |
| `0` | Success, including a current document |
| `1` | `check` found a change that `update` would make |
| `2` | Invalid arguments, document, path, settings, or curation constraint |
| `3` | Git or filesystem operation could not supply the required facts |
| `130` | Interrupted |
