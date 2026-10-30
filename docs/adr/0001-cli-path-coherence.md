# ADR 0001: Coherence of CLI paths and repository selection

- Status: Provisional; proposed directions, not an accepted decision
- Date: 2026-10-29
- Scope: `treestamp [tui]`, `--document`, `--print`, and the document arguments to `check` and `update`

## Context

Treestamp distinguishes the Git repository, the subtree being documented, and the document containing the treestamp. The CLI exposes these concepts through arguments whose path semantics are easy to confuse.

Currently, `treestamp [tui] [PATH]` treats `PATH` as a filesystem location from which to discover the containing Git repository. It does not select that location as the tree root. The tree root dialog independently defaults to `.`. Passing a subdirectory of the current repository can therefore appear to do nothing, while passing a location in another checkout selects that checkout.

The `--document` argument and the positional document arguments to `check` and `update` are repository-root-relative. This is coherent with stored document identities and the editor's explicitly repository-relative dialogs, but conflicts with normal shell expectations. From `docs/`, `treestamp check README.md` currently refers to the repository's top-level README, while `cat README.md` refers to `docs/README.md`.

The working product assumption is that a treestamp documents the repository in which its containing document resides, optionally displaying a subtree of that repository. Cross-repository documentation is not an intended use case. Copying or printing output does not itself establish a destination document.

The current contract remains documented in [Design](../design.md#command-line). This ADR records possible changes without implementing them.

## Provisional direction 1: CLI document paths should probably be relative to cwd

Resolve explicitly supplied CLI document paths relative to the current working directory, then convert the result to a canonical repository-relative identity for internal use. Apply this consistently to `--document`, `check DOCUMENT`, and `update DOCUMENT`.

For example, when invoked from `docs/`, the proposed behavior would be:

```bash
treestamp check README.md      # docs/README.md
treestamp check ../README.md   # the repository's top-level README.md
```

The editor dialogs can remain explicitly repository-root-relative, and stored roots and hidden paths should remain repository-relative. User-facing filesystem resolution and persisted identity need not use the same convention.

This would require accepting parent components that still resolve inside the chosen repository; simply removing the existing traversal check would be insufficient. Repository-boundary, symlink, and submodule checks must still apply to the resolved destination.

Open questions:

- Should an omitted document mean `README.md` in cwd or the repository's top-level README? The former is consistent with explicit input; the latter preserves current convenience. Any difference must be deliberate and visible in help text.
- Should absolute document paths be accepted when they resolve inside the permitted repository?
- Does cwd select the repository, or can an explicitly supplied document select its own containing repository? The latter supports opening another checkout without changing directories but makes document discovery authoritative.

## Provisional direction 2: `--document` should probably exclude explicit `PATH`

If the positional repository selector remains, reject invocations that explicitly supply both it and `--document`, including when `--print` is used. Do not silently choose precedence between two possible sources of repository context. An omitted `PATH` must remain distinguishable from an explicitly supplied `.`.

Under the same-repository assumption, the document and its repository should supply a coherent source of scope; a second repository-selection argument appears unnecessary. An existing document also already records its tree root, so `PATH` should not become an implicit override of that root.

This is a proposed interface simplification, not a logical requirement of the assumption: both arguments could identify the same repository, and the current implementation resolves the document within the selected repository. The case for mutual exclusion is avoiding redundant authority and ambiguous expectations, rather than fixing an established cross-repository write bug.

Before adoption, decide whether `--document` immediately opens a document or continues to seed the interactive Load dialog. It currently opens directly with `--print`, while interactive startup still offers New or Load. Mutual exclusion would need an understandable meaning in both modes.

## Open decision 3: Should positional `PATH` exist at all?

| Option | Benefits | Costs |
| --- | --- | --- |
| Remove `PATH`; discover the repository from cwd | Fits the repository-local workflow; simplifies invocation; removes the misleading suggestion that a subtree argument selects the tree root | Breaks existing invocations and scripts; opening another checkout requires changing directories unless document-based discovery is adopted |
| Keep `PATH` as a repository locator | Supports opening another checkout without changing directories; useful to wrappers and launchers; preserves existing invocations | Provides little value inside the current repository; subtree arguments appear ineffective; requires explicit rules for interaction with `--document` |
| Replace `PATH` with an explicit repository option | Makes repository selection more discoverable and distinguishes it from a document or tree root | Retains the extra concept and validation rules; still changes existing syntax; may be unnecessary for the intended workflow |

The current preference is removal, but no option is accepted by this ADR. If retained, help should explicitly say that any path within a checkout selects its containing repository and does not select a subtree. Repurposing `PATH` to mean tree root would be a separate behavioral change, not a clarification of the existing argument.

## Consequences and adoption criteria

Any accepted change needs coordinated CLI help, documentation, regression tests, and a breaking-change release note. In particular, changing document resolution could select a different existing file when invoked from a subdirectory; that compatibility impact is more significant than merely rejecting a removed argument.

Before implementation, settle the default document location, the authority for repository discovery, the supported path spellings, and the interaction between interactive startup and `--print`. Tests should cover repository-root and subdirectory invocation, explicit and omitted documents, conflicting arguments, and preservation of repository boundaries.

`--target` and `--compare` remain independent Git snapshot and move-detection options for `check` and `update`. These proposals do not change their semantics, the document format, or the web editor.
