# ADR 0001: Coherence of CLI paths and repository selection

- Status: Accepted and implemented
- Date: 2026-10-29
- Decision updated: 2026-10-30
- Scope: CLI document paths, repository selection, and editor startup

## Context

Treestamp distinguishes the Git repository, the subtree being documented, and the document containing the treestamp. A treestamp documents the repository containing its document, optionally displaying a subtree. CLI paths need to follow filesystem conventions, while stored paths need a stable identity independent of the caller's working directory.

A separate repository selector creates two possible sources of context when a document is also supplied. A positional directory can also be mistaken for the tree root. Selecting the repository through the document avoids this ambiguity.

## Decision

Explicit CLI document paths resolve from cwd or accept absolute paths. The document selects its containing repository. The CLI converts the resolved path to a repository-relative identity for internal use.

`--load DOCUMENT` selects the TUI's Load action and opens the document directly. The name describes an action and distinguishes loading from choosing a write destination. Without `--load`, the editor uses cwd's repository and presents New/Load. The selected or loaded document determines the tree root; there is no separate CLI repository selector.

`check DOCUMENT` and `update DOCUMENT` use the same path resolution. Their document arguments are positional because the command supplies the action. Omitted document arguments use the repository-root README, allowing repository-wide checks from subdirectories. Explicit paths follow cwd even when the filename is `README.md`.

Bare `--print` uses the repository-root README, generating a new tree if it is absent or unmarked. With `--load`, printing requires a valid existing treestamp. Neither form writes a document.

Editor-session paths and stored configuration are repository-relative; rendered entries are relative to the selected tree root. A session's document operations are confined to its selected repository. CLI discovery rejects symlinks before normalizing parent components. An initialized nested repository or submodule can own an explicitly selected document; an uninitialized submodule remains a boundary within its parent repository.

The [CLI reference](../cli-reference.md) is the source of command syntax, examples, and detailed operating rules.

## Alternatives considered

| Option | Benefit | Cost and decision |
| --- | --- | --- |
| Positional repository `PATH` | Opens another checkout without changing directories | Looks like a subtree selector and competes with document-based selection; rejected |
| Explicit repository option | Makes repository selection explicit | Adds a separate concept and precedence rules without a demonstrated need; rejected |
| Document-owned repository, otherwise cwd | Matches the Load action and repository-local workflow; supports documents in other checkouts | Requires filesystem path resolution before repository discovery; accepted |

## Consequences

The CLI and the editor use different path bases for different purposes: cwd for explicit filesystem inputs, and the repository root for persistent identities and editing operations. Repository-root defaults for omitted documents are deliberate and must be visible in help text.

Regression tests cover explicit and omitted documents, root and subdirectory invocation, direct TUI loading, other checkouts, symlinks, and repository boundaries. `--target` and `--compare` operate within the selected document's repository. The document format and web editor are unaffected.
