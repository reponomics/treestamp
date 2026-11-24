# CLI reference

This reference describes the current commands, path rules, and editor behavior. See [Design](design.md) for the document format and architecture; [ADR 0001](adr/0001-cli-path-coherence.md) records the rationale for the CLI design.

## Commands

```text
treestamp [--print]
treestamp new [PATH] [--print]
treestamp load [DOCUMENT] [--print]
treestamp check [DOCUMENT] [--target REF] [--compare REF]
treestamp update [DOCUMENT] [--target REF] [--compare REF] [--skip-notes-transfer]
treestamp help [COMMAND]
treestamp --version
treestamp --help
```

With no command, `treestamp` loads a valid treestamp from `README.md` in the current working directory (cwd), or starts a new tree rooted at cwd if that README is missing or contains no treestamp. It opens the editor directly. An unreadable document or malformed treestamp fails instead of silently starting over. Bare invocation outside a Git repository fails.

Use `new` to start fresh regardless of an existing README, or `load` to require an existing treestamp. These commands replace the former `tui` verb and `--load` flag; there is no terminal source picker or New/Load screen.

Use `treestamp help` (equivalent to `treestamp --help`) for general help, or `treestamp help <command>` for command-specific help. For example, `treestamp help new` describes source selection and `treestamp help update` describes unattended maintenance. Help works outside Git. Within the TUI, press `?` for keyboard help.

## Repositories, paths, and snapshots

| Input | Interpretation |
| --- | --- |
| `new` | A fresh tree rooted at cwd |
| `new PATH` naming an existing directory | A fresh tree rooted at that directory |
| `new PATH` naming a regular file | A fresh tree rooted at the file's parent; the file is not loaded or selected for writing |
| `load`, `check`, or `update` without a document | `README.md` in cwd |
| Explicit document argument | A cwd-relative or absolute file path; selects its containing repository |

From `docs/`, `treestamp load` opens `docs/README.md`, and `treestamp new` creates a tree rooted at `docs/`. The same directory's `treestamp check` and `treestamp update` operate on its README. Use `../README.md` explicitly to operate on the repository's top-level README. A loaded document retains its saved repository-relative root: a README in `docs/` can describe the whole repository.

Explicit source and document paths can select another checkout even when cwd is outside Git. A new-tree path must exist. Paths may include `..`, but symlinks are refused, including traversed components before parent normalization. An initialized nested repository or submodule owns sources selected within it; uninitialized submodules remain boundaries. Stored root, hidden-path, and special-path identities remain repository-relative regardless of the caller's cwd.

New trees and interactive or automatic updates use a captured staged Git index by default. Stage additions, deletions, and renames before these operations. Untracked files are absent, and unstaged changes are not incorporated. Subsequent interactive edits use the captured snapshot. Documents themselves are read from disk. Treestamp does not stage or commit files or fetch remote history. Extraction with `load --print` reads the saved document without acquiring a current Git snapshot.

## Interactive editor

```bash
treestamp
treestamp new docs
treestamp load docs/structure.md
treestamp load /path/to/another/checkout/README.md
```

New treestamps start with the selected root's immediate children and collapsed directories. Loading reads an existing treestamp and updates an in-memory draft against the captured index while preserving supported curation. Invalid sources or documents report an error before opening the editor. The editor identifies the selected root; an empty staged tree explains that files need to be staged.

| Keys | Action |
| --- | --- |
| Arrow keys, Space, Home/End, Page Up/Down | Navigate and expand or collapse directories |
| `h`, `H`, `S` | Hide/unhide an entry, reveal hidden entries for browsing, unhide all |
| `a` | Edit the selected entry's annotation |
| `c`, `s`, `t` | Toggle counts, cycle Unicode/ASCII/list style, toggle attribution footer |
| `w` | Write back to the loaded document (loaded sessions only) |
| `v`, `y`, `p` | Preview, copy the draft, print it and exit |
| `?`, `q` / Escape | Help, quit |

When an interactive load leaves notes without their original rows, a **Transfer notes?** modal offers to move them to the updated tree or continue without them. Enter starts transfer; Escape continues without those notes. New trees and loads without unmatched notes open the editor directly. No document changes until you choose Write.

The transfer view remains queue-based for this release. One source appears above the destination tree. Navigate with the arrow keys, press Enter to transfer the note to the selected row, or `s` to skip it. A directory belongs on a directory; other notes belong on files or other leaf entries. Opening folders only changes browsing. Transferring reveals the destination in the saved draft so its annotation is included. `H` reveals hidden destinations for browsing. Replacing an existing annotation requires confirmation. `?` shows full paths and notes when a line is truncated.

Transferring a directory also carries its pending annotated descendants recursively when their full relative paths and entry kinds match. An unannotated removed directory can stand for its annotated descendants. Missing paths, kind changes, conflicting notes, and destinations already holding another transferred note remain for individual decisions. Skipping a directory leaves its descendants available individually. Matching never uses just a basename and does not guess renamed paths.

`u` undoes the last decision, including every note carried by a directory transfer. Resolving the queue opens the editor automatically. Escape skips remaining items and starts editing. Transfer is a one-time step for each document load; skipped notes are omitted when writing. A navigable list remains a [follow-up for both interfaces](ui-flow.md#follow-up-navigable-note-list).

Run `make reconcile-demo` from a development checkout for a disposable example with moved files, a directory with nested notes, and a removed entry. Its writes stay in a temporary repository.

New treestamps are exported with Copy or Print; paste the complete block into your document. Copy includes markers and any configuration comment. Loaded sessions can Write directly back to the original document while preserving surrounding bytes. New-tree sessions have no write destination. To start another session, exit and invoke the desired command. Unwritten changes require confirmation before quitting.

## Print without opening the editor

```bash
treestamp --print
treestamp new docs --print
treestamp load docs/structure.md --print
```

`load --print` validates and extracts the complete treestamp region as it exists in the document. It preserves its markers, metadata, notes, formatting, and line endings. It does not capture or refresh the source tree, or check whether notes need transfer. Repository/path validation still applies, including Git metadata checks that enforce submodule boundaries. A stale document prints its saved tree. A missing, unmarked, or malformed document fails.

`new --print` generates a new treestamp for the selected root from the staged Git index. Bare `--print` extracts from cwd's README if it contains a valid treestamp, or generates a fresh tree at cwd if the README is absent or unmarked. A malformed or empty marked region remains an error.

Printing writes to stdout without changing a document. It accepts neither `--target`, `--compare`, nor `--skip-notes-transfer`. Run an explicit `update` first to change the saved document, then `load --print` to extract that result. Printing from inside the interactive editor exports its current draft, including edits made during that session. Shell redirection writes independently of treestamp; do not redirect output over a document the command must read.

## Check and update

```bash
treestamp check
treestamp check docs/structure.md --target HEAD
treestamp update docs/structure.md --compare HEAD
treestamp update docs/structure.md --skip-notes-transfer
treestamp check README.md --target HEAD --compare HEAD~1
```

Both commands require an existing, valid treestamp. `check` computes the proposed automatic replacement without writing it. It prints `Current: …` and exits `0` when unchanged, or a unified diff and exits `1` when an update would change the document, including generated formatting. If the replacement would omit notes, it reports that separately on stderr. It does not require transfer decisions or accept the override flag.

`update` prepares automatic changes, then checks whether any original notes would be omitted. If so, it exits nonzero without writing. Open the document with `treestamp load DOCUMENT` to transfer those notes interactively, or explicitly use `--skip-notes-transfer` to accept their omission. The override retains matched and successfully moved notes. A successful update replaces only the managed region, preserves surrounding bytes and line endings, and prints `Updated: …` or `Current: …`.

`--target REF` selects a local Git tree instead of the staged index. `--compare REF` enables supported rename matching from that reference to the target snapshot. Automatic matching happens before the unmatched-note guard. Notes on vanished or kind-changed paths, conflicting destinations, or destinations absent from the resulting draft still require attention. Directory annotations do not follow renames automatically. Interactive loading does not perform rename detection, and extraction performs no matching.

Supported formatting differences are preserved before comparison: zero or one blank line after the start marker, between configuration and tree, and before the end marker, plus equivalent TOML formatting when validated configuration values are unchanged. These differences alone do not fail `check`. Changed configuration is regenerated with compact array wrapping at an 80-character target and loses its comments; oversized individual entries stay intact. See the [document format](design.md#document-format).

## Output and exit status

When writing directly to a terminal, CLI output escapes control characters from document context and diagnostics; tabs and line breaks retain their layout. Redirected output retains its original bytes and line endings.

Output uses UTF-8, preserving undecodable Git bytes through redirected output. New regions use LF; extraction retains the stored region's LF or CRLF convention. Exported snippets omit a file-level UTF-8 BOM. Writing into an existing document preserves its line-ending convention and any original BOM. Diagnostics go to stderr.

| Exit status | Meaning |
| --- | --- |
| `0` | Success, including a current document |
| `1` | `check` found a change that `update` would make |
| `2` | Invalid arguments, document, path, settings, or an update requiring a note-transfer decision |
| `3` | Git or filesystem operation could not supply required facts |
| `130` | Interrupted |
