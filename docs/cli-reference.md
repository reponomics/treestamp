# CLI reference

## Commands

```text
treestamp [--print]
treestamp new [DIRECTORY] [--print]
treestamp load [DOCUMENT] [--print]
treestamp check [DOCUMENT]
treestamp update [DOCUMENT] [--skip-notes-transfer]
treestamp export [--load DOCUMENT] --format svg (--stdout | --output PATH) [--theme adaptive|light|dark] [--replace]
treestamp export [--load DOCUMENT] --format markdown --stdout
treestamp help [COMMAND]
treestamp --version
treestamp --help
```

The CLI is designed such that when it is invoked with implicit arguments or commands, it applies default assumptions about what behavior is most likely to serve the most common use case, which is considered to be: creating a treestamp whose root is the current working directory (`cwd`), or loading a treestamp from the file that's most likely to have one, `./README.md`. `treestamp new` is equivalent to `treestamp new .`; `treestamp load` is equivalent to `treestamp load ./README.md`; and `treestamp` on its own does the following: if `./README.md` contains treestamp markers, it tries `treestamp load ./README.md`, and fails if the loaded treestamp is malformed; else, it does `treestamp new .`; if invoked outside of a git repo altogether, it also fails.

Paths can be absolute or relative to cwd and can select another checkout. `new` requires an existing directory; use `load` for a document. Paths may include `..` but cannot pass through symlinks. To work inside a nested repository or initialized submodule, select it directly; a parent repository's tree cannot extend into it.

New trees and updates use a snapshot of the Git index. Stage additions, deletions, and renames before creating or updating a treestamp. The editor keeps that snapshot for the session; reopen it to pick up later staged changes.

## Interactive editor

```bash
treestamp
treestamp new docs
treestamp load docs/structure.md
treestamp load /path/to/another/checkout/README.md
```

New treestamps show the selected directory's immediate children, with subdirectories collapsed. Loading updates a draft of the saved tree while retaining its annotations, hidden entries, and expanded directories where possible.

| Keys | Action |
| --- | --- |
| Arrow keys, Space, Home/End, Page Up/Down | Navigate and expand or collapse directories |
| `h`, `H`, `S` | Hide/unhide an entry, reveal hidden entries for browsing, unhide all |
| `a` | Edit the selected entry's annotation |
| `c`, `s`, `t` | Toggle counts, cycle Unicode/ASCII style, toggle attribution footer |
| `w` | Write back to the loaded Markdown or SVG document (loaded sessions only) |
| `e` | Export a separate SVG file or copy SVG source |
| `v`, `y`, `p` | Preview text, copy Markdown, print Markdown and exit |
| `?`, `q` / Escape | Help, quit |

If a loaded tree has notes whose original paths are gone or have changed kind, a **Transfer notes?** dialog offers to move them to the updated tree. Enter starts transfer; Escape continues without those notes. Otherwise, the editor opens directly. The document is unchanged until you choose Write.

The transfer view presents one source note at a time above the destination tree. Navigate with the arrow keys, press Enter to transfer the note to the selected row, or `s` to skip it. A directory belongs on a directory; other notes belong on files or other leaf entries. Opening folders only changes browsing. Transferring reveals the destination in the saved draft so its annotation is included. `H` reveals hidden destinations for browsing. Replacing an existing annotation requires confirmation. `?` shows full paths and notes when a line is truncated.

Transferring a directory also carries its pending annotated descendants recursively when their full relative paths and entry kinds match. An unannotated removed directory can stand for its annotated descendants. Missing paths, kind changes, conflicting notes, and destinations already holding another transferred note remain for individual decisions. Skipping a directory leaves its descendants available individually.

`u` undoes the last decision, including every note carried by a directory transfer. Resolving the queue opens the editor automatically. Escape skips remaining items and starts editing. Transfer is a one-time step for each document load; skipped notes are omitted when writing.

Textual treestamps are exported with Copy Markdown or Print; paste the complete block into your document. Copy includes markers and configuration. Write to document updates the loaded source: it preserves surrounding Markdown prose or replaces the complete SVG from its embedded data. New trees have no source write target. Export SVG (`e`) offers Save SVG, Copy SVG, and Cancel, without adopting the export destination or clearing unsaved changes. The dialog retains the loaded SVG appearance, or uses Adaptive for a new export. Adaptive produces one file for light and dark pages, without inferring a theme from the terminal. It shows a textual notice instead of a graphical preview. A different existing SVG requires replacement confirmation; intervening changes refuse the write. Unwritten changes require confirmation before quitting.

## Print without opening the editor

```bash
treestamp --print
treestamp new docs --print
treestamp load docs/structure.md --print
```

`--print` writes a complete treestamp block to stdout without opening the editor or changing a document:

- `load --print` extracts the saved Markdown block unchanged, or renders the textual treestamp embedded in SVG metadata, even if its tree is stale. A missing, unmarked, or malformed document fails. To refresh the saved tree first, run `update`.
- `new --print` generates a tree for the selected directory from the staged Git index.
- Bare `treestamp --print` loads from cwd's `README.md` if it contains a treestamp, or generates a new tree at cwd if the README is absent or unmarked. A malformed treestamp remains an error.

Do not redirect output over the document being loaded: the shell can truncate it before treestamp reads it.

## SVG export

```bash
treestamp export --load README.md --format svg --output assets/treestamp.svg
treestamp export --load assets/treestamp.svg --format svg --stdout
treestamp export --load assets/treestamp.svg --format markdown --stdout
treestamp check assets/treestamp.svg
treestamp update assets/treestamp.svg
```

`export` loads and reconciles the source against the staged index, then produces a separate artifact. With no `--load`, it uses cwd’s README when available, otherwise a new tree rooted at cwd. Choose `--stdout` explicitly, or use `--output` with a repository-relative `.svg` path whose parent already exists. Existing destinations require `--replace`; the loaded source is never a valid export destination. Use `update` or TUI Write for that. `--theme` selects `adaptive`, `light`, or `dark`. Adaptive embeds both ink colors in one transparent SVG and selects them with an internal `prefers-color-scheme` media query. Without `--theme`, loaded SVG appearance is retained and other inputs use Adaptive. Markdown export supports stdout only, for manual insertion into a document. Exporting does not alter the loaded source. If refreshing would omit unmatched notes, export stops before producing output. Use `treestamp load DOCUMENT` to transfer notes and write the result first, or explicitly omit them with `treestamp update DOCUMENT --skip-notes-transfer` before exporting.

Save the SVG in the repository and add its README reference manually:

```markdown
![Repository tree](assets/treestamp.svg)
```

Treestamp does not follow, create, or update that reference. SVG source contains a complete textual treestamp in metadata and can be loaded again. Its drawing is regenerated from that metadata: manual visual edits, an unsupported visual style fallback, or a new renderer can make `check` report a change before editing. Updating replaces the drawing; a subsequent check with the same renderer is clean.

## Check and update

```bash
treestamp check
treestamp check docs/structure.md
treestamp update docs/structure.md
treestamp update docs/structure.md --skip-notes-transfer
```

Both commands read an existing, valid treestamp from disk and compare it with the captured index of its repository. With no document argument, they use `README.md` in cwd. `check` computes the proposed automatic replacement without writing it. It prints `Current: …` and exits `0` when unchanged, or a unified diff and exits `1` when an update would change the document, including generated formatting. If the replacement would omit notes, it reports that separately on stderr.

`update` retains notes at matching paths with the same entry kind; it does not infer renames. If any notes would be omitted, it exits nonzero without writing. Use `treestamp load DOCUMENT` to transfer those notes interactively, or `--skip-notes-transfer` to omit them while retaining matched notes. A successful update replaces only the managed region in Markdown, preserving surrounding bytes and line endings, or regenerates the complete SVG using its retained appearance and line endings. It prints `Updated: …` or `Current: …`.

`check` accepts the [supported blank-line and TOML formatting variations](design.md#document-format). If configuration values change, the configuration is regenerated and its comments are lost.

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
