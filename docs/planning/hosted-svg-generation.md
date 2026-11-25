# Hosted SVG generation

Status: implemented; retained as planning context.

## Contract

The hosted editor edits a decoded treestamp against a repository snapshot. SVG is an export representation. Opening, editing, note transfer, reset, and change detection are independent of SVG renderer availability. Source format supplies initial export preferences, not a separate editing workflow.

Hosted change detection compares decoded document state, including exact paths, notes, hidden entries, folds, and document settings. Reconciliation changes remain visible against the decoded source. The post-transfer baseline for Discard remains distinct from that source comparison. SVG appearance belongs to export preferences and result selection.

Source SVG drawing bytes are irrelevant to hosted change detection. Loading reads the embedded document; export generates a new drawing. Local file-write conflict checks remain in the local publication layer.

## Export interaction

Export starts with Markdown selected, including for an SVG source. Selecting SVG initiates generation after pending edits settle. Leaving Export resets the view and cancels pending browser work. Returning starts at Markdown again.

One request produces complete Automatic, Light, and Dark SVG variants. The renderer shares document preparation and layout across them. The browser retains the bundle for the active export view and selects complete outputs without modifying their markup. Appearance switches are immediate and make no server request. Copy and Download use the selected variant, including its saved appearance metadata. Loaded appearance initializes the selector; other inputs start with Automatic.

| State | Experience |
| --- | --- |
| Preparing | Loading state in Export; Tree remains available. |
| Temporarily busy | For `503 svg_busy` or `429`, preparation remains pending with a waiting message. Retry honors `Retry-After`, adds jitter, and stays within a 30-second deadline covering active requests and waits. |
| Complete | Preview, Copy, and Download use the same selected variant. |
| Unable to complete | Export explains the error and offers Try again. Invalid input and output-size limits are reported without automatic retries. Accepted edits remain intact. |

Leaving SVG output, leaving Export, or opening another document cancels requests and retries. Late results cannot replace a newer result. Document changes invalidate the bundle. App theme and preview zoom preserve it. Appearance selection uses only the current bundle and never starts generation.

## Execution and verification

Only export uses the bounded background rendering thread and shared render-time budget. There is no unbounded server queue. Canceled browser requests remain accounted for until admitted server work finishes. The background thread shares CPU and memory with the service; responsiveness requires testing with actual edit requests under expensive rendering load.

Each variant retains the existing SVG size limit. The bundle has a bounded total size. Renderer errors produce no partial success. Server-wide generated-output caching remains separate; correct operation does not depend on cache hits.

Acceptance checks cover equivalent Markdown/SVG editing and dirty state; successful editing while export is occupied, exhausted, or failing; one shared document preparation and layout per bundle; instant appearance switching without HTTP; deadline and cancellation behavior; late-response rejection; and matching preview/copy/download bytes and metadata.

Current behavior is documented in [UI flow](../ui-flow.md) and [Design](../design.md).
