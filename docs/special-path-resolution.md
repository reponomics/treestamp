# Resolve special filenames by row

Status: implemented in the current source. Special-path registrations identify rows directly; the backtracking resolver and its limits are removed. This note records the original problem and the replacement format.

## Original problem

Treestamp separates filenames from annotations with the exact delimiter `  # ` (two spaces, a hash, and a space). A filename can itself contain that delimiter. The former `special_paths` metadata recorded the full paths of such displayed entries, but did not identify their rows.

The former resolver in [codec.py](../src/treestamp/codec.py) considered both a registered filename and an ordinary filename followed by an annotation. It searched combinations of these interpretations to establish a unique tree. A choice near the beginning could cause all subsequent ordinary rows to be visited again. With several ambiguous rows, this produced combinatorial work until the branch limit was reached; `MAX_IDENTITY_BRANCHES` limited branching, not the length or total cost of those repeated traversals.

Before row-based resolution, local measurements with the 100-registration ceiling enabled used special filenames such as `special00  # suffix`, followed by ordinary filenames such as `ordinary0000`. Each document contained the corresponding path registrations and a flat Unicode tree:

| Special entries | Following ordinary entries | Document bytes | Parse time |
| --- | --- | --- | --- |
| 1 | 400 | 9,355 | 0.006 s |
| 10 | 100 | 2,932 | 1.601 s |
| 10 | 400 | 9,832 | 4.570 s |

These were successful local `parse_document` calls, not measurements of a production outage or timings of the current parser. They demonstrated that neither the 100-registration ceiling nor the hosted 1 MiB document cap resolved the backtracking problem. [The hosted service](../web/src/treestamp_web/preview.py) parses documents synchronously inside an asynchronous request handler, so an expensive parse can block other requests on the same worker. Repository size is not the relevant threshold: a README can describe these entries even when they do not exist, because parsing precedes reconciliation with the actual repository tree. Rendering also invokes the parser for its round-trip check, so new trees and edits were exposed to the same backtracking cost.

## Format

Each special path is associated with its exact printed row:

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

`row` is the zero-based index of a physical tree row, with the root at 0. Boundary markers, metadata, and code fences are excluded. Unicode, ASCII, and list styles use the same indexing. Paths remain repository-relative and retain the existing string or `git_bytes` representation.

The parser builds a lookup by row and visits the tree rows once. On a registered row, it validates the full path against the parent established by indentation, matches that path's filename using the current style's escaping, and parses only the suffix as type information, counts, and annotation. It does not try another filename interpretation. Unregistered rows use the ordinary row parser. The parser rejects duplicate row or path registrations, invalid indices (including the root), nonexistent rows, parent or filename mismatches, and registrations whose filenames do not contain the delimiter. Metadata selects an interpretation; it never bypasses validation.

The renderer generates row indices and registrations from the same traversal that emits the rows. The round-trip check still verifies exact identities and facts. Row-based resolution replaces the backtracking resolver, its branch limit, and the 100-registration ceiling. This removes combinatorial identity search; it is not a claim that every parser operation has linear complexity.

## Supported editing and transition

Annotation text is the only part of a tree that may be edited by hand (see the [document format](design.md#document-format)). Annotation edits do not change row indices or registered identities. Treestamp regenerates registrations after expansions, collapses, hiding, reordering, and other generated structural changes.

Only displayed entries whose own names contain the delimiter receive registrations. Hidden entries retain their exact paths in `hidden` instead, and descendants of collapsed directories have no printed rows to register. Ordinary children of specially named directories use the parent identity established by parsing that directory. Regeneration after structural changes updates every affected row index.

The old path-only registration format is rejected with an explicit regeneration error; there is no backtracking compatibility parser. Recreate these treestamps from the repository using the editor. Documents without special registrations remain valid.

## Acceptance checks

- Round-trip overlapping registered names, including the file/directory example above, in all three styles and with non-default roots and byte-encoded paths.
- Preserve identities when only annotations change, including annotations containing the delimiter.
- Verify that generated structural edits refresh row indices and still round-trip.
- Reject malformed, stale, duplicate, and old path-only registrations explicitly.
- Verify that the ten-special-plus-many-ordinary case resolves each row once, using an operation count rather than a timing threshold. Verify that more than 100 special entries no longer require the old ceiling.
