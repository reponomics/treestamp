<div align="center">
    <picture>
        <img src="https://raw.githubusercontent.com/reponomics/treestamp/main/assets/TREESTAMP_BANNER.png" alt="treestamp banner">
    </picture>
</div>

<br>

![OSSF-Scorecard Score](https://img.shields.io/ossf-scorecard/github.com/reponomics/treestamp?style=flat&label=OpenSSF%20Scorecard)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15900/baseline)](https://www.bestpractices.dev/projects/15900)
[![CodeQL](https://github.com/reponomics/treestamp/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/reponomics/treestamp/actions/workflows/github-code-scanning/codeql)


# treestamp

Turn your repository into a directory tree for your README. Choose what to show, add short notes, and copy the result—from your terminal or browser.

## Quickstart

### 1. Generate a treestamp

**In your browser:** [Open the web editor](https://treestamp.reponomics.org/), enter a public GitHub repository URL, and choose **Load repo → Create treestamp**. Nothing to install.

**In your terminal:** Requires Python 3.11+ and Git. Install from PyPI:

```bash
python -m pip install treestamp
```

Then open the repository you want to document:

```bash
cd /path/to/your/project
treestamp
```

Choose **New document** and accept `.` for the repository root. The terminal editor uses staged files, so stage your source changes before opening it.

### 2. Edit the tree

Expand the useful parts, hide the noise, and add a note. Both editors show you the tree as you work.

**Terminal — hide, annotate, preview.**

![Terminal editor: hide a directory, annotate the entry point, and preview the finished tree.](https://raw.githubusercontent.com/reponomics/treestamp/main/assets/demos/terminal.gif)

**Web — click to edit, then copy the Markdown.**

![Web editor: expand source files, hide tooling, add a note, and copy the complete treestamp.](https://raw.githubusercontent.com/reponomics/treestamp/main/assets/demos/web.gif)

### 3. Add it to your README

Choose **Copy** in the terminal editor or **Copy treestamp** on the web, then paste into your README. The copied block already includes the Markdown fence and Treestamp markers—keep the whole block so you can reopen it later.

````markdown
<!-- treestamp:start -->
```sh
./
├── docs/ (2 files)
├── src/  # Application code
│   ├── app.py
│   ├── search.py
│   └── storage.py
├── LICENSE
└── README.md
```
<!-- treestamp:end -->
````

Hidden entries also produce a small configuration comment; keep that with the copied tree. The web editor exports to your clipboard and never writes to GitHub.

<details>
<summary>Write directly from the terminal editor</summary>

Add these empty markers to your README, starting in column one:

```html
<!-- treestamp:start -->
<!-- treestamp:end -->
```

Choose **Write to existing** in the terminal editor and enter `README.md`. Treestamp fills the region and preserves the surrounding text. **Write new file** creates a separate document instead.

</details>

## Check your README automatically

`treestamp check README.md` checks whether the tree matches the repository. It never writes to the document and exits with code `1` when the tree needs attention. Open the document in an editor to review it.

**GitHub Actions:** after checking out your repository and setting up Python 3.11+, add this step:

<!-- x-release-please-start-version -->
```yaml
- name: Check the README tree
  run: |
    python -m pip install "treestamp==0.2.0"
    treestamp check README.md
```
<!-- x-release-please-end -->

**Local pre-commit:** add this to `.pre-commit-config.yaml`, then run `pre-commit install`:

<!-- x-release-please-start-version -->
```yaml
repos:
  - repo: https://github.com/reponomics/treestamp
    rev: v0.2.0
    hooks:
      - id: treestamp-check
```
<!-- x-release-please-end -->

Both examples pin the latest release. Run the check for source changes too, not just changes to Markdown.

<details>
<summary>Snapshots, paths, and existing documents</summary>

Choose **Load document** in either editor to reopen a treestamped README. The terminal editor reads the selected local repository's Git index; the web editor reads a public GitHub repository's default-branch HEAD. Both keep a frozen snapshot for the editing session. A failed load keeps your accepted draft.

Document paths are relative to the selected repository root, even when displaying a subtree. The terminal accepts another checkout with `treestamp /path/to/repository`. Paths outside that repository, symlink document paths, and paths crossing into submodules are not supported. Treestamp never stages or commits files.

New trees start with immediate children and collapsed directories. Counts include hidden children. Symlinks and submodules appear as leaves. Choose Unicode, ASCII, or Markdown-list output in the editor. Annotations are single-line notes; unsupported filenames or annotations are rejected before output is written or copied.

Web snapshots are cached temporarily; load the repository again if one is no longer available. See [privacy](https://github.com/reponomics/treestamp/blob/main/PRIVACY.md).

</details>

<details>
<summary>Windows</summary>

Use a terminal and font that display Unicode tree characters, or choose ASCII output. Treestamp emits UTF-8; printed output uses LF line endings, while writing into an existing document preserves its line endings. Windows filesystem restrictions still apply. See [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md) for development setup.

</details>

## Project Structure

Maintained by treestamp.

<!-- treestamp:start -->
<!-- treestamp:config
hidden = [".dockerignore", ".gitignore", ".nvmrc", ".pre-commit-config.yaml", ".pre-commit-hooks.yaml", ".python-version", ".tool-versions", "CHANGELOG.md", "LICENSE", "Makefile", "PRIVACY.md", "osv-scanner.toml", "pyproject.toml", "src/treestamp/__init__.py", "src/treestamp/__main__.py", "src/treestamp/py.typed", "uv.lock", "vex"]
-->
```sh
./
├── .github/ (8 files, 2 folders)
├── assets/ (2 files, 1 folder)
├── docs/ (6 files)
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
├── web/  # Hosted editor: a FastAPI adapter over the same package
│   ├── scripts/ (3 files)
│   ├── src/ (1 folder)
│   ├── tests/ (14 files, 2 folders)
│   ├── Dockerfile
│   ├── README.md
│   ├── fly.preview.toml
│   ├── fly.toml
│   ├── package.json
│   └── pyproject.toml
└── README.md
```
<!-- treestamp:end -->

## Development and support

[Contributing](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md) · [Maintenance](https://github.com/reponomics/treestamp/blob/main/docs/MAINTENANCE.md) · [Governance](https://github.com/reponomics/treestamp/blob/main/docs/GOVERNANCE.md) · [Design](https://github.com/reponomics/treestamp/blob/main/docs/design.md) · [Security assessment](https://github.com/reponomics/treestamp/blob/main/docs/security-assessment.md) · [Verifying releases](https://github.com/reponomics/treestamp/blob/main/docs/verifying-releases.md) · [Changelog](https://github.com/reponomics/treestamp/blob/main/CHANGELOG.md) · [Privacy](https://github.com/reponomics/treestamp/blob/main/PRIVACY.md)

Report bugs through [GitHub issues](https://github.com/reponomics/treestamp/issues), vulnerabilities through [private security reporting](https://github.com/reponomics/treestamp/security/advisories/new), and conduct concerns to [conduct@reponomics.org](mailto:conduct@reponomics.org).

[MIT licensed](https://github.com/reponomics/treestamp/blob/main/LICENSE). Before `1.0`, interfaces and the document format may change between releases.
