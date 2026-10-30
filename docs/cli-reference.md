# CLI reference

This reference describes the current CLI. [ADR 0001](adr/0001-cli-path-coherence.md) discusses provisional changes to path handling; those proposals are not implemented. See [Design](design.md) for the document format and architecture.

## Commands

```text
treestamp [tui] [PATH] [--document DOCUMENT] [--print]
treestamp check [DOCUMENT] [--target REF] [--compare REF]
treestamp update [DOCUMENT] [--target REF] [--compare REF]
treestamp --version
treestamp --help
```

With no command, `treestamp` opens the TUI. `tui` can also be omitted before its options: `treestamp --print` and `treestamp tui --print` are equivalent. Use `treestamp tui --help`, `treestamp check --help`, or `treestamp update --help` for command-specific help.

## Repositories, paths, and snapshots

| Input | Current interpretation |
| --- | --- |
| TUI positional `PATH` | A filesystem location used to discover its containing Git repository; defaults to cwd, accepts absolute paths, and resolves relative paths from cwd |
| `--document DOCUMENT` | A document path relative to the selected repository root; defaults to `README.md` |
| `check DOCUMENT` / `update DOCUMENT` | A document path relative to the repository containing cwd; defaults to `README.md` |
| TUI tree root and document dialogs | Paths relative to the selected repository root |

Passing `treestamp tui ./src` selects the repository containing `src`; it does not select `src` as the rendered tree root. Choose that subtree in the New document dialog. The root dialog accepts spellings such as `./src/` and stores the canonical `src` path. Currently, positional `PATH` and `--document` may be supplied together.

Document paths remain repository-root-relative even when invoked from a subdirectory. For example, from `docs/`, `treestamp check README.md` still checks the repository's top-level README. Absolute document paths, parent traversal such as `../README.md`, symlink paths, and paths crossing into another repository or submodule are rejected.

The default source is a captured Git index, not the working tree. Stage additions, deletions, and renames before opening or checking a treestamp. Untracked files are absent, and unstaged changes are not incorporated. New or Load captures a snapshot; subsequent edits use that snapshot until another New or Load operation. The containing document is read from disk, not from the index. Treestamp does not stage or commit files or fetch remote history.

## Interactive editor

```bash
treestamp
treestamp tui /path/to/another/checkout
treestamp --document docs/structure.md
```

Startup offers **New document** or **Load document**. `--document` supplies the Load dialog's initial path; it does not bypass this choice. New document starts with the selected root's immediate children and collapsed directories. Load reads a valid existing treestamp and updates its draft against the captured index while preserving supported curation.

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
treestamp --document docs/structure.md --print
```

`--print` writes the complete treestamp to stdout without changing a document. With explicit `--document`, the file must contain a valid treestamp; its updated draft is printed. Without `--document`, a valid treestamp in the default README is loaded, while an absent README or one without markers starts a new tree. Malformed or empty marked regions are errors, not requests to initialize a tree.

Printing does not accept `--target` or `--compare`. Shell redirection writes independently of treestamp; do not redirect output over a document the command must read.

## Check and update

```bash
treestamp check
treestamp check docs/structure.md --target HEAD
treestamp update docs/structure.md --compare HEAD
treestamp check README.md --target HEAD --compare HEAD~1
```

Both commands require an existing, valid treestamp. `check` computes the same replacement as `update` without writing it. It prints `Current: …` and exits `0` when unchanged, or a unified diff and exits `1` when an update would change the document, including generated formatting. `update` replaces only the managed region, preserves surrounding bytes and line endings, and prints `Updated: …` or `Current: …`.

`--target REF` selects a local Git revision instead of the captured index. `--compare REF` supplies the earlier revision for Git rename detection. For example, `--compare HEAD` can preserve annotations across staged renames; after committing a rename, select an appropriate earlier comparison revision.

Annotation transfer is best effort: supported moves must remain within the selected subtree, destination annotations take precedence, and hiding and collapse choices are respected. Directory annotations are not transferred by rename detection. Without `--compare`, annotations are preserved at unchanged paths but do not follow moves. TUI loading and `--print` do not perform rename detection.

## Output and exit status

Printed output uses UTF-8 and LF line endings. Writing into an existing document preserves its line-ending convention. Diagnostic errors go to stderr.

| Exit status | Meaning |
| --- | --- |
| `0` | Success, including a current document |
| `1` | `check` found a change that `update` would make |
| `2` | Invalid arguments, document, path, settings, or curation constraint |
| `3` | Git or filesystem operation could not supply the required facts |
| `130` | Interrupted |
