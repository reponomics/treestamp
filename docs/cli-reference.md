# CLI reference

See [Design](design.md) for the document format and architecture, and [ADR 0001](adr/0001-cli-path-coherence.md) for the rationale behind repository selection.

## Commands

```text
treestamp [tui] [--load DOCUMENT] [--print]
treestamp check [DOCUMENT] [--target REF] [--compare REF]
treestamp update [DOCUMENT] [--target REF] [--compare REF]
treestamp help [COMMAND]
treestamp --version
treestamp --help
```

With no command, `treestamp` opens the TUI. `tui` can also be omitted before its options: `treestamp --print` and `treestamp tui --print` are equivalent.

Use `treestamp help` (equivalent to `treestamp --help`) for general help, or `treestamp help <command>` (equivalent to `treestamp <command> --help`) for command-specific help. For example, `treestamp help tui` describes the editor options, and `treestamp help check` describes the drift checker. Help works outside a Git repository and exits without opening the editor. Within the TUI, press `?` for keyboard help.

## Repositories, paths, and snapshots

| Input | Interpretation |
| --- | --- |
| `--load DOCUMENT` | A cwd-relative or absolute document path; opens it directly and selects its containing repository |
| Explicit `check DOCUMENT` / `update DOCUMENT` | A cwd-relative or absolute document path; selects its containing repository |
| Omitted document for `check`, `update`, or `--print` | The repository-root `README.md` in the repository containing cwd |
| TUI startup without `--load` | The repository containing cwd; opens a visual folder/document chooser |
| TUI source chooser | Folders and documents on disk within the selected repository |

Explicit CLI document paths follow filesystem conventions. From `docs/`, `treestamp check README.md` checks `docs/README.md`, while `treestamp check ../README.md` checks the repository's top-level README. Bare `treestamp check` selects the top-level README. A document can select another checkout even when cwd is outside any repository.

CLI document paths may include `..`, but symlinks are refused, including traversed components before parent normalization. A document in an initialized nested repository or submodule selects that repository. Paths into an uninitialized submodule are rejected. The visual chooser is currently confined to its starting repository. Symlinks and crossings into other repositories or submodules are rejected when preparing a selection.

To open another repository, pass a document in it with `--load` or change directories before starting treestamp. Within the chooser, select a folder to choose the tree root without typing its path.

The default source is a captured Git index, not the working tree. Stage additions, deletions, and renames before opening or checking a treestamp. Untracked files are absent from the generated tree, and unstaged changes are not incorporated. Accepting a folder or document captures a snapshot; subsequent edits use that snapshot for the session. The containing document is read from disk, not from the index. Treestamp does not stage or commit files or fetch remote history.

## Interactive editor

```bash
treestamp
treestamp --load docs/structure.md
treestamp tui --load /path/to/another/checkout/README.md
```

Without `--load`, startup shows one visual source tree. Selecting a folder offers **Create treestamp here**; selecting a regular file offers **Load treestamp from document**. Arrow keys navigate and expand folders, and Enter accepts the selected source. The chooser reads the working filesystem, including untracked documents, but the editable tree still comes from the staged Git index. Failed loads keep the document selected and report the error; they never silently create a new tree.

`--load DOCUMENT` opens the document directly, bypassing the chooser. An invalid explicit load reports an error without launching the editor. New trees start with the selected root's immediate children and collapsed directories. Loading reads a valid existing treestamp and updates its draft against the captured index while preserving supported curation.

| Keys | Action |
| --- | --- |
| Arrow keys, Space, Home/End, Page Up/Down | Navigate and expand or collapse directories |
| `h`, `H`, `S` | Hide/unhide an entry, reveal hidden entries for browsing, unhide all |
| `a` | Edit the selected entry's annotation |
| `c`, `s`, `t` | Toggle counts, cycle Unicode/ASCII/list style, toggle attribution footer |
| `w` | Write back to the loaded document (loaded sessions only) |
| `v`, `y`, `p` | Preview, copy the complete treestamp, print it and exit |
| `?`, `q` / Escape | Help, quit |

When loading a document leaves annotations without their original rows, the terminal editor asks whether to place them in the updated tree. Enter accepts; Escape continues into the editor without them. This happens for both explicit `--load` and documents selected through the opening flow. New documents and loads without removed annotations open the editor directly. Headless printing and updating do not show the prompt.

During placement, one source stays in a single line above a separator; the rest of the view is the destination tree. Navigate with the arrow keys, press Enter to place the source on the selected row, or `s` to skip it. A directory belongs on a directory; other annotations belong on files or other leaf entries. Opening folders only changes the browser. Placing an annotation expands its destination's ancestors in the actual draft so that the annotation will be written. `H` reveals hidden destinations for browsing; placing on one also unhides it. Replacing an existing annotation requires confirmation. `?` shows the full source, destination, and annotation when a line is truncated.

Placing a directory also carries its pending annotated descendants recursively when their full paths relative to that directory and entry kinds match. An unannotated removed directory can stand for its annotated descendants. Missing paths, kind changes, different existing annotations, and destinations already holding another placed annotation remain for individual decisions. Skipping a directory leaves its descendants available individually. Matching never uses just a basename, and it does not guess renamed paths.

`u` undoes the last decision, including every annotation carried by a directory placement. When the queue is exhausted, the editor opens automatically. Escape skips the remaining items and starts editing. Placement is a one-time step for each document load; there is no placement mode to reopen during editing. Skipped annotations are omitted when writing. No file changes until you choose Write in the main editor.

Run `make reconcile-demo` from a development checkout for a disposable example with moved files, a directory with nested annotations, and a deliberately removed entry. Its writes stay in a temporary repository.

New trees are exported with Copy or Print; paste the complete block into your document. Copy includes markers and any configuration comment. When a session starts by loading a document, Write to document saves directly back to that document and preserves content outside its boundary markers. There is no write action for a new-tree session and no destination picker. Folder creation and document loading are available only in the opening chooser. Unwritten changes require confirmation before quitting.

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

Supported formatting differences are preserved before that comparison: zero or one blank line after the start marker, between configuration and tree, and before the end marker, plus equivalent TOML configuration formatting when its validated values are unchanged. These differences alone do not fail `check`. When configuration values change, `update` regenerates the configuration with compact array wrapping at an 80-character target and discards its comments. Oversized individual entries stay intact. See [ADR 0002](adr/0002-formatter-compatible-documents.md) for the rationale and limits.

`--target REF` selects a local Git revision in the document's repository instead of its captured index. `--compare REF` supplies the earlier revision for Git rename detection. For example, `--compare HEAD` can preserve annotations across staged renames; after committing a rename, select an appropriate earlier comparison revision.

Annotation transfer is best effort: supported moves must remain within the selected subtree, destination annotations take precedence, and hiding and collapse choices are respected. Directory annotations are not transferred by rename detection. Without `--compare`, annotations are preserved at unchanged paths but do not follow moves. TUI loading and `--print` do not perform rename detection.

## Output and exit status

Output uses UTF-8. New regions use LF line endings; printing or copying a loaded region preserves its LF or CRLF convention and supported formatting. Exported snippets omit a file-level UTF-8 BOM. Writing into an existing document preserves its line-ending convention and any original BOM. Diagnostic errors go to stderr.

| Exit status | Meaning |
| --- | --- |
| `0` | Success, including a current document |
| `1` | `check` found a change that `update` would make |
| `2` | Invalid arguments, document, path, settings, or curation constraint |
| `3` | Git or filesystem operation could not supply the required facts |
| `130` | Interrupted |
