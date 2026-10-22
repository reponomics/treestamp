<div align="center">
    <picture>
        <img src="https://raw.githubusercontent.com/reponomics/treestamp/main/assets/TREESTAMP_BANNER.png" alt="treestamp banner">
    </picture>
</div>

# treestamp

Treestamp is an editor for creating and maintaining directory trees for project documentation. It can be accessed locally from the terminal, or online via the web editor. Easily select which files and folders to include, add brief annotations to tree entries, and produce an output in a variety of Markdown-friendly formats. The application preserves the structure of existing treestamps, and it can also be integrated into a project's automation, making it easier to keep repository documentation up to date.

## Install and edit

Requires Python 3.11+ and Git. Install from a source checkout with `python -m pip install .`. PyPI installation will be available after the initial release. You can also try the [preview web editor](https://treestamp-preview.fly.dev/).

```bash
treestamp                         # open the editor in the current repository
treestamp /path/to/repository      # open another repository
treestamp --document README.md     # prefill the Load document path
treestamp --print                  # print the prepared treestamp and exit
```

Choose **New document** to start a tree or **Load document** to open an existing one. New asks for a tree root, defaulting to `.`; Load reads the root from the document. Opening an existing tree prepares updates in memory. Edit the draft, then Write to save it. A failed load keeps your current draft; Refresh replaces it only after the replacement loads and parses successfully.

Local snapshots use the Git index, so stage source changes before opening. Untracked source paths do not participate, although the document itself may be untracked. Editing stays on the captured snapshot until you reload. Treestamp never stages or commits files.

Document paths and stored tree paths are relative to the selected repository root, even when launched from a nested directory or displaying a subtree. Absolute document paths, `..` traversal, symlinks, and paths crossing into another repository or submodule are rejected. Use the positional repository argument to select another repository. Shell redirection of Print output is controlled by your shell.

The web editor loads public GitHub repositories at their default-branch HEAD and edits a frozen snapshot. It exports content for you to copy; it never writes to your GitHub repository. Cached snapshots and their links are temporary. An unavailable snapshot must be loaded again; the editor does not silently switch an existing draft to a different commit. See [privacy](https://github.com/reponomics/treestamp/blob/main/PRIVACY.md).

## Editor controls

| Key | Action |
|---|---|
| Arrow keys | Navigate and expand or collapse directories |
| `h` / `H` | Hide a child / inspect hidden entries |
| `a` | Add or edit a single-line annotation |
| `c` / `s` | Toggle counts / change tree style |
| `N` / `l` | Start a new document / load a document |
| `n` / `w` | Write a new file / write into an existing document |
| `y` / `p` | Copy / print the complete treestamp; Print exits the terminal editor |
| `q` / `?` | Quit / show keyboard help |

The web editor provides the corresponding load, edit, and copy controls. Local file writing is available in the terminal editor.

New trees show the root and its immediate tracked children. Child directories start collapsed. Updates add non-hidden immediate children beneath expanded directories, keep collapsed directories collapsed, and preserve surviving annotations. Counts include hidden children. Symlinks and submodules appear as leaves and are not traversed. Unicode, ASCII, and Markdown list styles are available.

## Write into a README

Add these markers where the tree belongs, then use Write:

```html
<!-- treestamp:start -->
<!-- treestamp:end -->
```

Markers must start in column one. Write preserves the marker lines and surrounding prose; creating a new document refuses to overwrite an existing file. Copy and Print include the whole managed region, including its metadata.

You can edit annotations directly in the printed tree using exactly `  # ` (two spaces, hash, space), followed by a single-line comment. Use an editor for tree structure and configuration changes. The optional `treestamp:config` block records the tree root, hidden paths, and generated entries for names that need disambiguation; style, expansion, annotations, and count visibility come from the printed tree.

Some Git filenames and symlink targets cannot be represented by the format. Loading checks the entire selected subtree, including hidden and collapsed descendants, and reports unsupported entries. Failed loads or invalid annotations retain the accepted draft. Output is validated before it is written or exported.

## Check and update

```bash
treestamp check README.md          # would updating change this document?
treestamp update README.md         # update and write the document
treestamp check --target HEAD
treestamp update --compare HEAD
treestamp update --target HEAD --compare HEAD~1
```

These commands default to `README.md` and the Git index. Check never writes. Update refreshes the tree and counts while preserving curation for surviving paths. Repeating Update against the same snapshot leaves the document unchanged. Run the commands inside the repository that owns the document.

`--target` selects a locally available commit instead of the index, including historical or unpublished commits. `--compare` supplies a reference for supported file-move detection and annotation transfer. These options apply to Check and Update, not editor startup.

Exit codes are `0` for success or a current document, `1` when Check finds a change, `2` for invalid input or usage, `3` for unavailable Git or filesystem information, and `130` for interruption. Failed operations do not partially write output.

## Automation

The pre-commit hooks are `treestamp-check` (check only) and `treestamp` (update). After the public repository is available, add this to `.pre-commit-config.yaml`, replacing the revision with a reviewed full commit SHA:

```yaml
repos:
  - repo: https://github.com/reponomics/treestamp
    rev: REPLACE_WITH_A_REVIEWED_PUBLIC_COMMIT
    hooks:
      - id: treestamp-check
```

Choose `id: treestamp` to update instead. Review and stage the changed README before retrying the commit. Both hooks run even when only source files change.

In GitHub Actions, install a chosen released version or reviewed public commit, then run `treestamp check README.md`. For this project's own source checkout, the [README check workflow](https://github.com/reponomics/treestamp/blob/main/.github/workflows/treestamp-check.yml) installs the checked-out package. The separate [update workflow](https://github.com/reponomics/treestamp/blob/main/.github/workflows/treestamp-update.yml) can open a draft README update PR. Headless printing and maintenance do not import Textual.

## Windows

Treestamp emits UTF-8 output; Print uses LF line endings, while updates preserve the existing document's line endings. Use a terminal and font that display Unicode tree characters, or choose ASCII style. Windows filesystem restrictions still apply to local paths. Contributor setup commands for Windows are in [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md).

## Project tree

<!-- treestamp:start -->
<!-- treestamp:config
hidden = [".dockerignore", ".gitignore", ".pre-commit-config.yaml", ".pre-commit-hooks.yaml", ".python-version", "src/treestamp/__init__.py", "src/treestamp/__main__.py", "src/treestamp/py.typed"]
-->
```sh
./
├── .github/ (7 files, 2 folders)
├── assets/ (1 file)
├── scripts/ (6 files)  # Installed-package acceptance
├── src/
│   └── treestamp/  # Shared model and terminal editor
│       ├── cli.py
│       ├── codec.py
│       ├── document.py
│       ├── editor.py
│       ├── errors.py
│       ├── gitio.py
│       ├── maintenance.py
│       ├── model.py
│       ├── session.py
│       ├── sources.py
│       ├── tui.py
│       └── tui_dialogs.py
├── tests/ (16 files)  # Contract and integration tests
├── web/ (6 files, 3 folders)  # Hosted editor: a FastAPI adapter over the same package
├── .nvmrc
├── CHANGELOG.md
├── LICENSE
├── MAINTENANCE.md
├── Makefile
├── PRIVACY.md
├── README.md
└── pyproject.toml
```
<!-- treestamp:end -->

## Development and support

See [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md) for setup and checks, [MAINTENANCE](https://github.com/reponomics/treestamp/blob/main/MAINTENANCE.md) for builds and deployment, and [CHANGELOG](https://github.com/reponomics/treestamp/blob/main/CHANGELOG.md) for release changes. Before `1.0`, interfaces and the document format may change between releases. MIT licensed.

Report ordinary bugs through [GitHub issues](https://github.com/reponomics/treestamp/issues), vulnerabilities through [private security reporting](https://github.com/reponomics/treestamp/security/advisories/new), and conduct concerns to [conduct@reponomics.org](mailto:conduct@reponomics.org).
