# ADR 0004: SVG at the document input/output boundary

Status: proposed; not an implemented format or an accepted compatibility promise.

Review: independently reviewed by a second agent on 2026-11-23 against the current model, session, document, and hosted code. Revisions incorporated subtree hidden-path conversion, symlink-only targets, existing text-preflight constraints, appearance preservation, document-level validation, and the requirement to ship both SVG reading and writing. The final review found no blocking architectural issue; exact schema and rendering choices remain open below. Human review is pending.

## Context

Treestamp currently exports Unicode, ASCII, and Markdown-list trees inside a managed Markdown region. The web editor draws continuous branches, while textual exports rely on box-drawing characters. We want a portable graphical format with the same continuous branches and enough structure to reopen it as a treestamp. This is a new artifact format, not merely another choice of textual branch characters.

Much of the existing text codec solves ambiguity between filenames, type suffixes, counts, and annotations. Generated graphical artifacts have a different contract: users are not expected to edit their visible labels as a way of editing the treestamp. Structured metadata can separate these fields explicitly. The importer still validates input, but need not infer identities or annotations from SVG text positions or delimiters.

The core model already separates tree facts from presentation. [`Node`](../../src/treestamp/model.py), [`TreeSession.printed_tree()`](../../src/treestamp/session.py), and [`Document`](../../src/treestamp/document.py) provide suitable inputs. The text codec and Markdown document writer have deliberate round-trip and managed-region contracts that should remain intact. [`treeGuides()`](../../web/src/treestamp_web/static/tree-view.js) provides the existing web branch topology; it is a useful reference for a platform-independent layout traversal.

## Proposed decision

Add SVG serialization at the output boundary. Any accepted internal document can be exported as SVG, regardless of its input format. Loading a textual treestamp and copying its SVG representation is the primary required workflow. Loading an SVG treestamp to update it is equally required. Ship the SVG reader, writer, and versioned structured metadata together as one first-class format; the reader and writer are separate adapters around the same internal model, not optional product capabilities. Preserve `Settings.style` as the existing text-style choice. Keep SVG appearance options separate from tree curation and text settings. Do not introduce a general renderer plugin system until a second graphical backend demonstrates a need for one.

### Rendering pipeline

```text
Markdown reader --+                         +-- Markdown writer
                  +-- internal tree/session-+
SVG reader -------+                         +-- SVG writer
                            ^
                     repository snapshot
```

Both readers produce the same document model for reconciliation and editing. Either writer can serialize the resulting accepted document. SVG loading must preserve the existing repository selection and refresh/update flow; it must not require a conversion through Markdown.

The new output boundary is conceptually `render_svg(document, appearance) -> str`. Parsing remains at the input boundary; the renderer consumes the internal model and does not inspect the source format. No editing-engine rewrite or intermediate text reparse is required. The first exporter accepts the sessions supported today: editor initialization still performs text-codec preflight, and hosted responses currently compose Markdown as well. SVG export alone does not remove those existing input restrictions; supporting graphical-only tree facts would be a later, separate change. The layout and SVG serializer should be pure Python modules alongside the text codec, independent of browser DOM, terminal widgets, network access, and Git access. The same implementation should serve CLI and hosted exports. Use actual line/path geometry with text elements; do not screenshot the web editor or place box-drawing glyphs on a larger canvas. The source is the accepted printed projection, never the temporary reveal-hidden view. Use the existing document-composition semantics: `printed_tree()` plus settings and saved hiding converted to repository-relative paths with `repo_path(path, settings.root)`. `TreeSession.saved_hidden()` is tree-relative; `Document.hidden` is repository-relative. This conversion matters for subtree exports.

A small layout representation makes future raster output possible without tying the tree engine to SVG. It should describe only what this renderer needs: row positions, label runs, branch segments, and dimensions. Bounds must account for names, annotations, optional counts, attribution, Unicode display, and font metrics. Font packaging or measurement is an implementation gate: an SVG must remain legible when embedded as an image without fetching the web app's fonts. Test a bundled, license-compatible font strategy against supported consumers before promising identical metrics. Avoid `foreignObject`, scripts, and external resource dependencies in generated artifacts.

### Required SVG round-trip: metadata and authority

Use one namespaced application-data element inside SVG's standard `metadata` element. The payload is versioned JSON containing explicit tree records, document settings, saved hiding, and appearance options. SVG supports application-specific metadata for round-tripping; [the SVG document-structure specification](https://www.w3.org/TR/SVG2/struct.html#MetadataElement) describes this use. An `<img>` embedding applies a restricted processing mode, reinforcing the choice of a self-contained drawing; see [SVG processing modes](https://www.w3.org/TR/SVG2/conform.html#processing-modes).

Define and test this schema before releasing SVG support. Metadata and a validated reader are part of the first release, not deferred enhancements. These are required data responsibilities, not final field names:

| Data | Contract |
| --- | --- |
| Format and schema version | Explicit treestamp identity and supported version; reject unsupported versions. |
| Ordered printed nodes | Exact tree-relative paths, node kinds, optional symlink targets, annotations, counts, and hierarchy. Derive display names from identity; do not use display strings as identifiers. |
| Document settings | Selected root, counts, attribution, and retained textual style for subsequent Markdown export. |
| Saved hiding | The same excluded-path information retained by a current Markdown document. |
| Appearance | Versioned graphical presentation options, independent of curation. |
| Optional provenance | Repository and commit information for context; never a substitute for the source snapshot or permission to fetch it automatically. |

Reuse `path_value()` and `read_path_value()` for exact Git identities, including the existing `git_bytes` representation. Define the same lossless treatment for targets that are not valid Unicode. JSON serialization must escape characters that cannot appear in XML text, and XML serialization must escape markup characters. Display labels use a separate readable escaping policy. Delimiter-looking filenames, whitespace, control characters, and invalid UTF-8 must not turn into ambiguous node identities.

Do not make a Markdown region the canonical metadata payload. That would retain the very row and delimiter parsing this format can avoid. A future Markdown export can be regenerated from the validated structured document through the existing text renderer.

On import, validate the supported payload and return an artifact-level result containing `(document, appearance)`; regenerate the visible representation from both. Graphical appearance remains outside `Document` and `Settings`, but must survive loading and re-export. SVG paths, text elements, colors, and positions are not parsed back into tree facts. Manual drawing edits are therefore discarded on regeneration, while valid changes to supported metadata are subject to ordinary model validation. Missing, duplicate, malformed, or unsupported metadata causes an explicit unsupported-artifact or invalid-artifact error. Do not silently guess from visible text or fetch linked resources.

No signature or checksum is required for the initial format. A checksum is not authentication and does not establish that the visible drawing corresponds to the data. The contract deliberately defines metadata as authoritative; an importer should explain that the treestamp is being restored from embedded data and show the regenerated preview. Integrity/authenticity mechanisms would need a separate requirement.

### Document round-trip; full-session archives are excluded

SVG reimport preserves the information in `Document`, including saved hiding, and the artifact appearance. It does not promise to restore the complete editing session. This is the same document-versus-session distinction that already applies to Markdown. [`TreeSession`](../../src/treestamp/session.py) explicitly keeps hidden annotations and descendant layouts in session memory while only `printed_tree` and `saved_hidden` belong in a document. Consequently, exported metadata may name excluded paths, just as Markdown does, but must not silently include hidden notes or the complete hidden/folded subtree.

With valid embedded metadata, the printed projection can be recovered from the artifact alone. Refreshing it against a repository, expanding omitted descendants, or restoring hidden files still requires the corresponding source tree and the existing reconciliation flow. The web session envelope depends on cached source data; embedding it does not make an export self-contained. A full-session archive would need the complete source snapshot plus curation and a distinct, explicit product contract. Defer that capability.

### Import and resource boundaries

An imported SVG is data, not executable markup. Extract the supported metadata with a bounded, non-networked parser, reject DTD/entity expansion, enforce payload/node/depth limits, and validate tree relationships, uniqueness, kinds, counts, paths, targets, and settings. Do not insert uploaded SVG markup into the browser DOM. Generate the displayed preview from validated data. Reuse existing validators where they express the same invariants; add a structured document decoder rather than routing through the text parser. In particular, preserve the existing root identity and collapsed-directory count rules and require `normalized_hidden(document) == document.hidden`, as the Markdown reader does. Supported metadata/appearance cannot request external resources; references elsewhere in the unconsumed drawing markup are never resolved or retained. This does not require a general SVG/CSS validator.

Metadata can be removed by image optimizers or export tools. Such an SVG remains an ordinary image but no longer qualifies as an editable treestamp artifact. A raster renderer could later share the layout, but arbitrary image import and metadata retention through image transformations are not implied by supporting image export.

### User interface and command boundaries

Tree remains the editing view; Markdown previews and copies the textual export. Add SVG preview and Copy SVG/Download SVG as graphical export actions, available for the same accepted session without reloading or converting the source. Copy SVG means copying serialized SVG markup; Download SVG saves those same bytes. Native image clipboard transfer is not part of this proposal. Keep graphical output separate from the Markdown text-style selector. Final placement needs a small UI design pass. A standalone SVG reader/writer must not reuse Markdown marker splicing or silently change the behavior of existing CLI `print`, `check`, or `update` commands. Add an explicit export entry point and a deliberate SVG load path after the container contract is tested.

## Delivery sequence

1. Review the paired input/output boundaries, document round-trip contract, and typography strategy.
2. Implement the structured metadata schema, SVG reader, and pure renderer with round-trip tests against existing `Document` inputs. These may be built incrementally internally, but all are required before presenting SVG as a supported format.
3. Expose SVG loading, preview, Copy SVG, and Download SVG for existing textual loads, SVG loads, and newly created trees. Add explicit CLI export/update adapters using the same core reader and renderer. Preserve current reconciliation and atomic-publication behavior.
4. Evaluate raster export only when needed. Full-session archives are outside this ADR.

This branch currently changes the landing illustration and restricts editing Settings to Tree. It does not implement these SVG stages.

## Acceptance criteria

For the paired format:

- A textual treestamp loaded through the current codec can be edited and copied/downloaded as SVG without changing its source format or reloading the repository. An SVG treestamp can be loaded, reconciled with the repository, edited, and exported as SVG or Markdown. Newly created trees use the same output paths.
- Copy SVG and Download SVG serialize the same accepted document and appearance. Failed exports preserve the accepted editing session.
- Branches join exactly across rows and stop at the correct last sibling; hidden entries and folded descendants are omitted from the drawing.
- Output dimensions accommodate long labels and annotations; deterministic typography is verified in direct SVG viewing and image embedding, including light/dark appearance and accessible title/description.
- CLI and hosted exports agree for the same document and appearance. Existing text-codec, Markdown-formatting, and reconciliation tests remain unchanged.

Required round-trip criteria:

- Structured metadata round-trips exact `Document` facts, including special paths, byte paths, all node kinds, counts, notes, and saved hiding, without parsing displayed text.
- Metadata includes only the declared document facts, not extra hidden notes or the complete source snapshot.
- Visible drawing changes never alter recovered tree facts. Missing/invalid metadata rejects clearly; valid metadata produces a regenerated preview.
- Imports reject invalid versions, duplicate application payloads, invalid trees, excessive resource use, entities, and external-resource requests in supported metadata/appearance without changing the accepted session.

## Alternatives and unresolved details

Adding `svg` to `Settings.style` would mix a container/media type with three text layouts and spread changes through parsers and Markdown export. Capturing the editor as an image would couple export to browser state and make CLI output harder to reproduce. Recovering data from SVG labels would recreate delimiter and layout ambiguity. Storing only the web envelope would falsely suggest durable source portability. A mandatory full snapshot would expand disclosure and size beyond today's document contract.

Before implementation, settle the portable font strategy, annotation wrapping, output-size limits, export-control placement, exact JSON schema and namespace identifier, payload limits, and SVG source-selection/update behavior. These are explicit follow-up design choices; this ADR does not claim they are already supported.
