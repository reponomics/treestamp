# ADR 0001: Coherence of CLI paths and repository selection

- Status: Accepted and implemented for the next release
- Date: 2026-10-29
- Decision updated: 2026-10-30
- Scope: `treestamp [tui]`, `--load` (replacing `--document`), removal of positional `PATH`, `--print`, and the document arguments to `check` and `update`

## Context

Treestamp distinguishes the Git repository, the subtree being documented, and the document containing the treestamp. Before this decision, the CLI exposed these concepts through arguments whose path semantics were easy to confuse.

In 0.3.x, `treestamp [tui] [PATH]` treated `PATH` as a filesystem location from which to discover the containing Git repository. It did not select that location as the tree root. The tree root dialog independently defaulted to `.`. Passing a subdirectory of the current repository could therefore appear to do nothing, while passing a location in another checkout selected that checkout.

The former `--document` argument and the positional document arguments to `check` and `update` were repository-root-relative. This was coherent with stored document identities and the editor's explicitly repository-relative dialogs, but conflicted with normal shell expectations. From `docs/`, `treestamp check README.md` referred to the repository's top-level README, while `cat README.md` referred to `docs/README.md`.

A treestamp documents the repository in which its containing document resides, optionally displaying a subtree of that repository. Cross-repository documentation is not an intended use case. Copying or printing output does not itself establish a destination document.

The implemented contract is documented in [Design](../design.md#command-line) and the [CLI reference](../cli-reference.md). This ADR records the decisions and their rationale.

## Decision

### Replace `--document` with `--load DOCUMENT`

`--load` expresses the user's action: select **Load document** from the TUI's opening New/Load choice and supply the document to load. It opens that document directly in the editor, bypassing the opening choice and path-entry dialog. It is not merely an initial value for a later dialog or an output destination.

Resolve a relative `--load` path from the current working directory, then discover the repository containing the document. That repository supplies the editing session's context, and the loaded treestamp supplies its tree root and curation.

For example:

```bash
treestamp --load docs/architecture.md
treestamp tui --load ../other-project/README.md
```

The second invocation selects the repository containing `../other-project/README.md`, regardless of whether cwd belongs to that repository. The document must contain a valid existing treestamp; an invalid load must not silently start a new document.

Without `--load`, discover the repository containing cwd and show the usual **New document** / **Load document** choice. `treestamp` with no command remains equivalent to `treestamp tui`.

### Remove positional repository `PATH`

Remove the positional repository locator from `treestamp [tui]`. Do not replace it with another repository-selection option. The repository is determined by the explicitly loaded document, or by cwd when no document is supplied.

This removes competing sources of repository context and the misleading suggestion that a positional directory selects a tree root. The earlier proposal to make `PATH` and `--document` mutually exclusive is superseded by removing `PATH`.

### Resolve CLI document paths from cwd

Apply the same cwd-relative resolution to explicit `check DOCUMENT` and `update DOCUMENT` arguments. Each command uses the repository containing its document. Their document arguments remain positional because the command already specifies the action.

For example, when invoked from `docs/`:

```bash
treestamp check README.md      # docs/README.md
treestamp check ../README.md   # the repository's top-level README.md
```

Convert the resolved document path to a canonical repository-relative identity for internal use. Parent components such as `..` must be interpreted at the CLI boundary before validating that identity; simply removing the internal traversal check would be insufficient.

### Retain repository-relative editor and stored paths

Tree roots and document paths entered within the editor, and paths stored in treestamp configuration, remain relative to the selected repository root. Rendered entries remain relative to the selected tree root. Loading a document from another checkout selects that checkout as the session's repository; it does not permit a session to document or write into an unrelated repository.

`--target` and `--compare` retain their existing Git snapshot and move-detection meanings for `check` and `update`, operating within the document's repository. These decisions do not change the document format or the web editor.

## Alternatives considered

| Option | Benefits | Costs and decision |
| --- | --- | --- |
| Keep positional `PATH` as a repository locator | Opens another checkout without changing directories; preserves existing invocations | Adds little inside the current repository, looks like a subtree selector, and competes with document-based selection; rejected |
| Replace `PATH` with an explicit repository option | Makes repository selection more explicit | Retains an extra concept and precedence rules without a demonstrated need; rejected |
| Select the repository from the loaded document, otherwise cwd | Matches the Load action and repository-local workflow; still opens documents in other checkouts | Breaks existing invocations and requires filesystem path resolution before repository discovery; accepted |

`--load` was chosen over `--document` because it names the opening-dialog action and distinguishes loading an existing treestamp from choosing a write destination.

## Defaults, discovery, and compatibility

Omitted document arguments to `check` and `update` retain the repository-root `README.md` default in cwd's repository. Explicit paths resolve from cwd. This deliberately preserves convenient repository-wide checks from subdirectories while making explicit paths match filesystem conventions.

Absolute CLI document paths are accepted. Symlinks are refused, including path components traversed before `..` normalization. A document in an initialized nested repository or submodule selects that repository as its owner; an uninitialized submodule is still a boundary and cannot supply a document within its parent repository. Once the repository is selected, existing checks protect repository-relative identities and writes.

`--load DOCUMENT --print` requires a valid existing treestamp and prints its updated draft. Bare `--print` retains the repository-root README default: it loads a valid treestamp, or starts a new tree if the README is absent or unmarked. Malformed or empty marked regions are errors. Printing is headless and does not establish a write destination.

There is no compatibility alias for `--document`, and positional repository arguments are rejected. Migration guidance names `--load` as the replacement and explains that explicit document paths now resolve from cwd. This change is made before the stable 1.0 interface.

## Consequences and acceptance criteria

The implementation includes coordinated CLI help, documentation, regression tests, and a breaking-change release note. Changing document resolution can select a different existing file when invoked from a subdirectory; that compatibility impact must be explained alongside the removed and renamed arguments.

Verify that explicit `--load` bypasses the opening choice, restores the existing treestamp, and selects the document's repository; omitted `--load` retains the chooser in cwd's repository; and positional repository arguments are rejected. Cover root and subdirectory invocation, paths into another checkout, invalid documents, explicit `check`/`update` paths, and repository-root defaults when arguments are omitted. Verify that editor paths, stored identities, repository boundaries, and `--target`/`--compare` semantics remain intact.
