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

treestamp is an editor for creating and maintaining directory trees for project documentation. Easily select which files and folders to include, and add brief annotations. The application reloads your treeestamp when you want to update it, and automated checks can notify you when there is any drift betweeen treestamp and the repository, making it easy to keep documentation up to date.

## Quickstart

### 1. Generate a treestamp

treestamp can be accessed locally in your terminal, or online via the web editor.

#### In the browser

[Open the web editor](https://treestamp.reponomics.org/); enter a public GitHub repository URL (or `OWNER/REPONAME` form); and choose **Load repo → Create treestamp**. The server will fetch the directory structure of the repository at the HEAD of the default branch, and render a basic tree as a starting point.

#### In your terminal

treestamp is available on PyPI. It requires Python 3.11+ and Git, and is distributed with a Textual TUI for cross-platform support.

```bash
python -m pip install treestamp
treestamp
```

Invoke it directly from anywhere within a Git repository (or pass the path to another repository via the `path` positional argument). You can also run it directly without a persistent installation:

```
pipx run treestamp
```

Choose **New document** and select the path where you want the root of the repository tree to be located (defaults to the repository root, `.`, but you can generate a treestamp for any sub-tree in the repository) - the treestamp root is a relative path from the repository's root.

> [!NOTE] 
> Paths in treestamp are always relative to the _repository root_, regardless of where the application is launched, where the document containing the treestamp is located, or where the root of the rendered tree is located.

> [!TIP] 
> The editor only recognizes git-tracked files, staged or committed, so stage/commit any changes before opening it.

### 2. Edit the tree

Use the editor to expand the important parts of the directory tree, hide the dotfiles or any other distractions, and add helpful notes.

**Terminal**

![Terminal editor: hide a directory, annotate the entry point, and preview the finished tree.](https://raw.githubusercontent.com/reponomics/treestamp/main/assets/demos/terminal.gif)

**Web Editor**

![Web editor: expand source files, hide tooling, add a note, and copy the complete treestamp.](https://raw.githubusercontent.com/reponomics/treestamp/main/assets/demos/web.gif)

### 3. Add it to your README

When first writing a treestamp to a document, choose **Copy** in the terminal editor or **Copy treestamp** on the web, then paste the block into your Markdown document. treestamp renders directory trees inside a pair of HTML comment boundary markers:

`<!-- treestamp:start -->`

`<!-- treestamp:end -->`

These markers help the application recognize existing treestamps, and make sure that everything outside the boundaries stays the same.

Paste the whole block, including the markers, anywhere in your document.

````html
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

#### The config block

The treestramp may also contain a `<!-- treestamp:config --->` block after the top boundary marker containing a list of paths that are in the git-tracked directory structure, but which the user has elected to hide in the rendered tree. A record of these is retained so that when the treestamp is reloaded, the application can remember: "don't render these in the output." (These hidden paths can always be viewed and unhidden in the editor interface.)

<details>
<summary>Alternate boostrapping method</summary>

Another way to write the initial treestramp is to simply place the boundary markers into the target document, like so:


```html
<!-- treestamp:start -->
<!-- treestamp:end -->
```

Then, you can go to the TUI editor and load that document, and it will recognize that as a valid treestamp block. Then, when you are ready to write the result, the application can write directly in between those blocks, without having to do any copy/paste.

</details>

### 4. Update an existing treestamp

To load an existing treestamp for editing, enter the path to the document containing the treestamp in the editor interface. The editor will find the boundary markers and load the treestamp with the same editorial decisions (hidden paths, collapsed directories, etc.). However, the following modifications will be applied to the draft when loaded into the editor:

(i) paths that are rendered in the tree but are no longer tracked in Git will be removed from the draft;

(ii) paths that are in the Git-tracked directory structure but not in the treestamp draft, _and are not included in the array of hidden paths_, will be added to the draft _if_ they are siblings of a directory that is not collapsed. (Newly added directories will be initialized as collapsed.)

The application is designed to help keep documentation up to date by removing stale paths, which positively misrepresent the state of the repository; add new paths when they appear, but in a conservative manner; and preserve the user's previous edits and decisions, as best as possible.

### Include a treestamp footer (optional)

treestamp is a very cool software, and you will probably want to let other people know that you're using it. Of course, you don't have to (we understand that sometimes it's cooler to keep things a secret), but if you want to include a small recognition in the footer of your treestamp, you can opt in to doing so by selecting **Add "Mainted with treestamp" footer** (or press <kbd>t</kbd> in the terminal). This will simply print the following line below the rendered tree, and before the closing boundary marker:

```markdown
Maintained with [treestamp](https://github.com/reponomics/treestamp)
```

## Check your README automatically

treestamp can help you keep your documentation up to date. `treestamp check` will compare the tree to the current state of the checkout, and exit 1 if the two are not in sync. Add it as a pre-commit hook, and you can be notified whenever the treestamp has drifted from the state of the repo. treestamp can automatically update the tree, but we recommend that if you wish to follow this method, use the automation as a drift checker, and then open the editor to update the treestamp according to your preferences.

**GitHub Actions:** after checking out your repository and setting up Python 3.11+, add this step:

<!-- x-release-please-start-version -->
```yaml
- name: Check the README tree
  run: |
    python -m pip install "treestamp==0.3.0"
    treestamp check README.md
```
<!-- x-release-please-end -->

**Local pre-commit:** add this to `.pre-commit-config.yaml`, then run `pre-commit install`:

<!-- x-release-please-start-version -->
```yaml
repos:
  - repo: https://github.com/reponomics/treestamp
    rev: v0.3.0
    hooks:
      - id: treestamp-check
```
<!-- x-release-please-end -->


<details>
<summary>Windows</summary>

Use a terminal and font that display Unicode tree characters, or choose ASCII output. Treestamp emits UTF-8; printed output uses LF line endings, while writing into an existing document preserves its line endings. Windows filesystem restrictions still apply. See [CONTRIBUTING](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md) for development setup.

</details>

## Project Structure

<!-- treestamp:start -->
<!-- treestamp:config
hidden = [".dockerignore", ".gitignore", ".nvmrc", ".pre-commit-config.yaml", ".pre-commit-hooks.yaml", ".python-version", ".tool-versions", "CHANGELOG.md", "LICENSE", "Makefile", "PRIVACY.md", "osv-scanner.toml", "pyproject.toml", "src/treestamp/__init__.py", "src/treestamp/__main__.py", "src/treestamp/py.typed", "uv.lock", "vex"]
-->
```sh
./
├── .github/ (8 files, 2 folders)
├── assets/ (2 files, 1 folder)
├── docs/ (6 files, 1 folder)
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

Maintained with [treestamp](https://github.com/reponomics/treestamp)
<!-- treestamp:end -->

## Development and support

[Contributing](https://github.com/reponomics/treestamp/blob/main/.github/CONTRIBUTING.md) · [Maintenance](https://github.com/reponomics/treestamp/blob/main/docs/MAINTENANCE.md) · [Governance](https://github.com/reponomics/treestamp/blob/main/docs/GOVERNANCE.md) · [Design](https://github.com/reponomics/treestamp/blob/main/docs/design.md) · [Security assessment](https://github.com/reponomics/treestamp/blob/main/docs/security-assessment.md) · [Verifying releases](https://github.com/reponomics/treestamp/blob/main/docs/verifying-releases.md) · [Changelog](https://github.com/reponomics/treestamp/blob/main/CHANGELOG.md) · [Privacy](https://github.com/reponomics/treestamp/blob/main/PRIVACY.md)

Report bugs through [GitHub issues](https://github.com/reponomics/treestamp/issues), vulnerabilities through [private security reporting](https://github.com/reponomics/treestamp/security/advisories/new), and conduct concerns to [conduct@reponomics.org](mailto:conduct@reponomics.org).

[MIT licensed](https://github.com/reponomics/treestamp/blob/main/LICENSE). Before `1.0`, interfaces and the document format may change between releases.
