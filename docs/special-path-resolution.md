# Resolve special filenames by row

Status: recommended design, not yet implemented. The current parser still uses backtracking and the 100-registration ceiling. This note records the remaining problem and the intended replacement.

## Problem

Treestamp separates filenames from annotations with the exact delimiter `  # ` (two spaces, a hash, and a space). A filename can itself contain that delimiter. The current `special_paths` metadata records the full paths of such displayed entries, but does not identify their rows.

In [codec.py](../src/treestamp/codec.py), `_registered_candidates` considers both a registered filename and an ordinary filename followed by an annotation. `_IdentityAssignments` then searches combinations of these interpretations to establish a unique tree. A choice near the beginning can cause all subsequent ordinary rows to be visited again. With several ambiguous rows, this produces combinatorial work until the branch limit is reached; `MAX_IDENTITY_BRANCHES` limits branching, not the length or total cost of those repeated traversals.

Local measurements with the 100-registration ceiling enabled used special filenames such as `special00  # suffix`, followed by ordinary filenames such as `ordinary0000`. Each document contained the corresponding path registrations and a flat Unicode tree:

| Special entries | Following ordinary entries | Document bytes | Parse time |
| --- | --- | --- | --- |
| 1 | 400 | 9,355 | 0.006 s |
| 10 | 100 | 2,932 | 1.601 s |
| 10 | 400 | 9,832 | 4.570 s |

These are successful local `parse_document` calls, not measurements of a production outage. They demonstrate that neither the 100-registration ceiling nor the hosted 1 MiB document cap resolves this problem. [The hosted service](../web/src/treestamp_web/preview.py) parses documents synchronously inside an asynchronous request handler, so an expensive parse can block other requests on the same worker. Repository size is not the relevant threshold: a README can describe these entries even when they do not exist, because parsing precedes reconciliation with the actual repository tree. Rendering also invokes the parser for its round-trip check, so new trees and edits can encounter the same cost.

## Recommended format

Associate each special path with its exact printed row:

```toml
special_paths = [
  { row = 1, path = "x  # y" },
  { row = 2, path = "x  # y  # z" },
]
```

For example, these registrations identify the following tree:

```text
./
├── x  # y  # z
└── x  # y  # z/
    └── ordinary
```

Row 1 is the file `x  # y` with annotation `z`; row 2 is the directory `x  # y  # z`. Matching registered filename prefixes alone cannot reliably distinguish them. The row association supplies the missing information directly.

Define `row` as the zero-based index of a physical tree row, with the root at 0. Exclude boundary markers, metadata, and code fences. Use the same indexing for Unicode, ASCII, and list styles. Paths remain repository-relative and retain the existing string or `git_bytes` representation.

The parser builds a lookup by row and visits the tree rows once. On a registered row, it validates the full path against the parent established by indentation, matches that path's filename using the current style's escaping, and parses only the suffix as type information, counts, and annotation. It does not try another filename interpretation. Unregistered rows use the ordinary row parser. Reject duplicate row or path registrations, invalid indices (including the root), nonexistent rows, parent or filename mismatches, and registrations whose filenames do not contain the delimiter. Metadata selects an interpretation; it never bypasses validation.

The renderer generates row indices and registrations from the same traversal that emits the rows. Retain the round-trip check to verify exact identities and facts. Remove the backtracking resolver, its branch limit, and the 100-registration ceiling once row-based resolution replaces them. This removes combinatorial identity search; it is not a claim that every parser operation has linear complexity.

## Supported editing and transition

Users may manually edit annotation text, but manually changing filenames, tree structure, or generated metadata is unsupported. Annotation edits do not change row indices or registered identities. Treestamp regenerates registrations after expansions, collapses, hiding, reordering, and other generated structural changes.

There is no requirement to preserve the old interpretation rules for an existing user base. Reject the old path-only registration format with an explicit regeneration error instead of retaining a backtracking compatibility parser. Documents without special registrations remain valid. Update generated fixtures and format documentation with the implementation.

## Acceptance checks

- Round-trip overlapping registered names, including the file/directory example above, in all three styles and with non-default roots and byte-encoded paths.
- Preserve identities when only annotations change, including annotations containing the delimiter.
- Verify that generated structural edits refresh row indices and still round-trip.
- Reject malformed, stale, duplicate, and old path-only registrations explicitly.
- Verify that the ten-special-plus-many-ordinary case resolves each row once, using an operation count rather than a timing threshold. Verify that more than 100 special entries no longer require the old ceiling.
