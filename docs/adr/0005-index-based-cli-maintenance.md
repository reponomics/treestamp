# Index-based CLI maintenance and directory-only creation

Status: accepted.

## Decision

Remove `--target REF` and `--compare REF`, along with local Git rename detection and automatic move-based annotation transfer. Local creation, interactive loading, `check`, and `update` use a captured Git index. `load --print` continues to extract the stored treestamp without updating it. `new [DIRECTORY]` accepts only an existing directory; a file argument is rejected instead of selecting its parent.

## Rationale

The CLI maintains documentation for the checkout being prepared for commit. Selecting a separate historical target adds another source of truth without a demonstrated maintenance need. Rename matching also requires a reliable baseline: documents do not record their generation commit, so a caller-selected comparison ref cannot establish which historical paths their annotations describe. Manual transfer provides an explicit choice when paths disappear. Requiring a directory for `new` makes the selected tree root unambiguous.

## Consequences

Scripts using either ref flag must use the staged index. Automatic updates retain notes at matching paths and entry kinds; `update` refuses to omit unmatched notes unless `--skip-notes-transfer` is supplied. Users can load the document interactively to transfer notes. Callers that passed a file to `new` must pass its parent directory explicitly. Hosted snapshot selection and manual note transfer are unchanged.
