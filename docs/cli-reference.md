# CLI reference

## Commands

```text
treestamp [--print]
treestamp new [DIRECTORY] [--print]
treestamp load [DOCUMENT] [--print]
treestamp check [DOCUMENT]
treestamp update [DOCUMENT] [--skip-notes-transfer]
treestamp help [COMMAND]
treestamp --version
treestamp --help
```

The CLI is designed such that when it is invoked with implicit arguments or commands, it applies default assumptions about what behavior is most likely to serve the most common use case, which is considered to be: creating a treestamp whose root is the current working directory (`cwd`), or loading a treestamp from the file that's most likely to have one, `./README.md`. `treestamp new` is equivalent to `treestamp new .`; `treestamp load` is equivalent to `treestamp load ./README.md`; and `treestamp` on its own does the following: if `./README.md` contains treestamp markers, it tries `treestamp load ./README.md`, and fails if the loaded treestamp is malformed; else, it does `treestamp new .`; if invoked outside of a git repo altogether, it also fails.

Explicit source and document paths can select another checkout even when cwd is outside Git. A new-tree path must be an existing directory; files are rejected. To create a tree for a file’s parent, pass that directory explicitly. To load a treestamp from a file, use `load`. Paths may include `..`, but symlinks are refused, including traversed components before parent normalization. An initialized nested repository or submodule owns sources selected within it; uninitialized submodules remain boundaries. Stored root, hidden-path, and special-path identities remain repository-relative regardless of the caller's cwd.

New trees and interactive or automatic updates use a captured staged Git index. Stage additions, deletions, and renames before these operations. Untracked files are absent, and unstaged changes are not incorporated. Subsequent interactive edits use the captured snapshot. Documents themselves are read from disk. Treestamp does not stage or commit files or fetch remote history.

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

The transfer view presents one source note at a time above the destination tree. Navigate with the arrow keys, press Enter to transfer the note to the selected row, or `s` to skip it. A directory belongs on a directory; other notes belong on files or other leaf entries. Opening folders only changes browsing. Transferring reveals the destination in the saved draft so its annotation is included. `H` reveals hidden destinations for browsing. Replacing an existing annotation requires confirmation. `?` shows full paths and notes when a line is truncated.

Transferring a directory also carries its pending annotated descendants recursively when their full relative paths and entry kinds match. An unannotated removed directory can stand for its annotated descendants. Missing paths, kind changes, conflicting notes, and destinations already holding another transferred note remain for individual decisions. Skipping a directory leaves its descendants available individually. Matching never uses just a basename and does not guess renamed paths.

`u` undoes the last decision, including every note carried by a directory transfer. Resolving the queue opens the editor automatically. Escape skips remaining items and starts editing. Transfer is a one-time step for each document load; skipped notes are omitted when writing.

Copy and Print export the current draft, including your edits, markers, and configuration. For a new treestamp, paste this complete block into your document. Loaded sessions can Write directly back to the original document while preserving surrounding bytes. New-tree sessions have no write destination. To start another session, exit and invoke the desired command. Unwritten changes require confirmation before quitting.

## Print without opening the editor

```bash
treestamp --print
treestamp new docs --print
treestamp load docs/structure.md --print
```

`--print` writes a complete treestamp block to stdout without opening the editor or changing a document:

- `load --print` extracts the saved block unchanged, even if its tree is stale. A missing, unmarked, or malformed document fails. To refresh the saved tree first, run `update`.
- `new --print` generates a tree for the selected directory from the staged Git index.
- Bare `treestamp --print` loads from cwd's `README.md` if it contains a treestamp, or generates a new tree at cwd if the README is absent or unmarked. A malformed treestamp remains an error.

Do not redirect output over the document being loaded: the shell can truncate it before treestamp reads it.

## Check and update

```bash
treestamp check
treestamp check docs/structure.md
treestamp update docs/structure.md
treestamp update docs/structure.md --skip-notes-transfer
```

Both commands read an existing, valid treestamp from disk and compare it with the captured index of its repository. With no document argument, they use `README.md` in cwd. `check` computes the proposed automatic replacement without writing it. It prints `Current: …` and exits `0` when unchanged, or a unified diff and exits `1` when an update would change the document, including generated formatting. If the replacement would omit notes, it reports that separately on stderr.

`update` retains notes at matching paths with the same entry kind; it does not infer renames. If any notes would be omitted, it exits nonzero without writing. Use `treestamp load DOCUMENT` to transfer those notes interactively, or `--skip-notes-transfer` to omit them while retaining matched notes. A successful update replaces only the managed region, preserves surrounding bytes and line endings, and prints `Updated: …` or `Current: …`.

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
