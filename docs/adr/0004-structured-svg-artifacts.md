# ADR 0004: SVG artifacts with an embedded textual treestamp

Status: accepted and implemented on the next-release branch; not yet a released compatibility promise.

Review: the initial structured-node proposal was independently reviewed on 2026-11-23. This revision replaces that payload with the existing textual document format at the maintainer's suggestion, makes visual styles independent, and clarifies GitHub embedding and ephemeral sessions. A fresh independent agent review checked this revision against the model, codec, document, and editor code. It identified count-preference inference and existing text-style representation limits; both are now explicit below. Final review found no remaining architectural blockers. The subsequent decision to repair the codec, retire list style, and define web/TUI export flows is recorded in the linked export experience; that addition received fresh independent review, with findings and resolutions recorded there. Rendering and compatibility gates remain implementation work.

## Context and decision

Treestamp already parses supported textual styles into a common document model and edits that model against a repository snapshot. A graphical format belongs at those input/output boundaries. It must support loading a textual treestamp and exporting SVG, and loading that SVG to edit and export either text or another SVG style. Reading and writing are required together in the first supported SVG release.

Use the complete existing textual treestamp as the authoritative SVG metadata payload. The payload includes the managed-region markers, configuration and special-path records, tree, and attribution, rather than only the visible rows. The current document codec already handles delimiter-looking filenames, byte identities, kinds, targets, annotations, counts, roots, and saved hiding. Reuse that contract instead of defining a second encoding of those facts. Surrounding README prose is not embedded.

Store the region's serialized bytes as uncompressed base64 inside a versioned, namespaced element under SVG's standard `metadata` element. Base64 is transport encoding, not a new tree format. A reader extracts and decodes the payload, then calls the existing `parse_document()`. A writer renders the current accepted document through the existing `render_region()` and packages it with a drawing. The drawing is generated from the document model; it is never reverse-engineered on import. SVG's [metadata element](https://www.w3.org/TR/SVG2/struct.html#MetadataElement) is intended to carry application-specific data.

This supersedes the initial proposal to encode ordered node records in JSON. Keeping the text parser is an advantage here: the existing ambiguity handling and validation remain authoritative. It does not couple SVG appearance to textual layout.

## Module boundaries and conversion contract

```text
Text document reader -------------------+
                                        |
SVG container reader -> text decoder ---+-> Document -> reconciliation/editor
                                                              |
                                               accepted export Document
                                                 /                   \
                                         text writer           SVG artifact writer
                                                             /                   \
                                                   text payload encoder     selected visual style
                                                                                  |
                                                                         layout -> SVG drawing
```

Every supported input format/style feeds the same model, and every supported output can be selected independently of that input. Successful conversion must preserve the existing document semantics. The current Unicode/ASCII rejection of syntax-colliding filenames is a codec defect to repair before SVG ships, not an accepted permanent limitation of conversion. Generalize exact-path disambiguation before retiring the unfenced list style. The remaining fenced Unicode and ASCII styles and every SVG style must support the same document identities. Retain round-trip rejection as a defensive guard against implementation faults, not as the expected behavior for supported names. “Arbitrary style” means any supported treestamp style; it does not promise recovery from unrelated SVG images without a treestamp payload. Source preservation for writes remains the job of the appropriate container adapter.

Keep the implementation in small, independently testable modules with these responsibilities (names to be settled during implementation):

| Boundary | Responsibility |
| --- | --- |
| Artifact dispatch | Identify a supported text or SVG container and select its reader/writer; distinguish malformed recognized artifacts from unrelated files. |
| Text document codec | Existing managed-region parsing, configuration, identity validation, and rendering. |
| SVG metadata codec | Envelope versioning, bounded XML extraction, base64 transport, and delegation to the text document codec. No layout knowledge. |
| Document composition | Produce the accepted document projection from a session, shared across output formats. |
| Visual style | Consume a validated document plus presentation options; produce layout primitives. No source-format parsing, Git access, or metadata serialization. |
| Layout and SVG drawing | Shared row/label/branch/dimension primitives and safe serialization of static SVG geometry/text. Styles may supply different layouts without replacing the metadata codec. |
| SVG artifact writer | Combine a generated drawing and the shared metadata envelope into one standalone file. |
| CLI and hosted adapters | Source selection, repository reconciliation, explicit output controls, and safe publication using the shared core. |

The first visual style uses continuous line/path geometry, with the web editor's [`treeGuides()`](../../web/src/treestamp_web/static/tree-view.js) as a topology reference. It must not screenshot the browser or emulate continuity with box-drawing text. A second SVG style should require only a style implementation, registration, and style-specific tests; it must reuse the artifact reader, metadata writer, and editor flow. A small internal registry/protocol is sufficient; a public plugin framework is unnecessary.

Keep `Settings.style` as the textual branch notation (`unicode` or `ascii` after the planned list removal). Both textual outputs use code fences; no fencing toggle is introduced. The list-removal policy and prerequisite codec repair are specified in the [export experience and release sequence](../planning/svg-export-flow.md). SVG style identifiers/options live outside `Document` and session curation. Readers return an artifact-level result containing the document and optional appearance preferences. Known styles retain their options on re-export. An unknown visual style must not prevent reading otherwise supported document metadata: load the document, report the appearance fallback, and offer the default or another supported style. An unknown document codec or envelope version is different and must fail explicitly rather than guess.

Document composition uses `TreeSession.printed_tree()`, settings, and document-level hiding. Convert `saved_hidden()` paths with `repo_path(path, settings.root)`: session paths are tree-relative while `Document.hidden` is repository-relative. Use the accepted printed projection, never the reveal-hidden display. SVG rendering consumes the model without reparsing the original source; text serialization remains necessary for its embedded payload. Existing text-codec preflight remains applicable, so SVG does not introduce graphical-only tree facts that the current text formats cannot represent.

## Payload, fidelity, and cost

The envelope declares its own version, a supported textual document codec identifier/version, base64 encoding, and graphical style/options. These are format versions, not installed package version numbers. A generator version may be diagnostic only. Freeze the exact namespace and envelope schema before implementation and test independent fixtures for compatibility.

Base64 covers the full current text domain more reliably than XML-escaped text. In a local probe, XML normalized CRLF and rejected a filename containing U+FFFF even though the existing text codec accepted it. Base64 preserved the exact region bytes in both cases. CDATA would not solve XML character restrictions. Do not add compression in the first version: it complicates limits and debugging for little benefit at ordinary sizes.

The document fidelity guarantee is the existing text codec's semantics, including its normalizations. It is not byte preservation of an arbitrary source README or serialization of every in-memory field. Current normalization includes annotation tabs, zero counts, and hidden paths below folded parents. Text alone can also lose an unobservable presentation preference: a root-only ASCII tree is inferred as Unicode, and count visibility defaults when no collapsed folder demonstrates it. Retain the two presentation preferences (`text_style` and `show_counts`) in the envelope, validate them with the existing settings rules, and apply them after parsing. These fields preserve output choices without duplicating the tree, roots, hidden paths, or annotations. They must agree with observable settings in the payload; contradictory supported metadata is invalid. For `text_style`, canonical region output before and after applying the preference must agree; this permits the root-only ASCII/Unicode ambiguity without overlooking distinguishable branch notation. For `show_counts`, reject false if any parsed node has positive file/directory counts; absence of counts permits either preference because zero or unknown counts are not evidence of a hidden-count choice. Do not use rendering alone to check count visibility: the current renderer prints stored node counts regardless of `Settings.show_counts`. These checks use the existing parsed model and renderer, without adding a second tree grammar. Graphical appearance stays separate.

Measurements on 2026-11-23 used the existing codec at `1b796c5` and Python 3.11.11. The probe extracted this repository's README region and constructed flat documents with 10, 100, and 1,000 descendants. Generated cases included root/per-entry notes, a collapsed directory with counts, a subtree root and hidden path, delimiter-looking and byte filenames, XML metacharacters, symlinks with escaped targets, and Git links. It asserted exact recovered region bytes and equality of parsed Documents with their inputs for those cases.

| Case | Region bytes | Base64 payload bytes | Metadata-only SVG bytes |
| --- | ---: | ---: | ---: |
| Current README (35 visible rows) | 1,709 | 2,280 | 2,456 |
| 10 descendants | 906 | 1,208 | 1,384 |
| 100 descendants | 7,618 | 10,160 | 10,336 |
| 1,000 descendants | 75,658 | 100,880 | 101,056 |

These are illustrative costs, not size limits. They exclude the drawing and final appearance/preferences fields. Base64 costs approximately one third beyond the textual bytes; relative to a drawing-only SVG, the entire embedded payload is additional. Long notes and deep indentation can exceed these examples. For 1,000 descendants, median local timings over 11 runs were approximately 27 ms for region rendering, 10 ms for parsing, and under 1 ms for container encoding/XML parsing/decoding. No production performance claim follows from this probe. The meaningful cost is duplicate document representation, which is acceptable for ordinary documentation artifacts; explicit input/output byte, node, depth, and layout limits remain required.

## Authority, validation, and session scope

Metadata is authoritative. Changing paths, labels, colors, or coordinates in the visible SVG does not edit the recovered treestamp. Valid changes to the embedded textual treestamp are accepted through ordinary parsing; unsupported or malformed data produces an actionable error. Import regenerates the preview from recovered data and explains that it uses embedded treestamp data. No checksum is needed: it would neither authenticate the file nor establish agreement between drawing and metadata.

Require exactly one supported payload at the specified location in an SVG document. Bound the entire file before parsing, reject DTD/entity expansion, disable network resolution, enforce strict base64 decoding and decoded-size limits, and delegate text decoding and structural validation to the existing document codec (including its current UTF-8/surrogateescape behavior). Keep node/depth limits and document root/count/hidden-path invariants. Never inject imported SVG markup into the DOM or resolve references from its drawing. Only validated presentation options reach the renderer; they cannot request external resources. Ignoring drawing content does not require building a general SVG/CSS validator.

An exported artifact contains the same printed tree and document-level hiding as text output. It must not add hidden notes, omitted descendants, repository snapshots, or cache-bound session envelopes. Updating against a repository and expanding omitted nodes still use the existing source-selection/reconciliation flow.

Sessions are ephemeral interactions: visit, edit, export, and leave. **Resume session** is a best-effort convenience after brief accidental navigation, dependent on browser state and cached source availability. It provides no persistence guarantee, and users are not instructed to save/share state-bearing URLs. SVG loading must work through its embedded document and ordinary repository selection without session recovery. Removing the resume convenience later must have no effect on any artifact codec or renderer. Session archives are outside this design.

An optimizer may remove metadata while leaving a perfectly viewable image. That file then lacks an editable treestamp payload and should be rejected as such. Read the original `.svg` file, not a rasterized preview or transformed image response.

## GitHub README compatibility

Use a standalone SVG from the first release. A README references it with an ordinary relative image link:

```markdown
![Repository tree](assets/treestamp.svg)
```

GitHub [documents relative image links](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#images) and [SVG image display](https://docs.github.com/en/repositories/working-with-files/using-files/working-with-non-code-files#rendering-and-diffing-images). GFM parsing alone is not the whole rendering contract: GitHub additionally [sanitizes rendered markup](https://github.com/github/markup#github-markup). A non-publishing probe of GitHub's [`POST /markdown` endpoint](https://docs.github.com/en/rest/markdown/markdown#render-a-markdown-document), with `mode=gfm` on 2026-11-23, stripped an inline `<svg><text>…</text></svg>` to plain text while preserving the image reference as an `img` element. Do not offer inline SVG markup as something users can paste into a README and expect to render.

The app opens the selected treestamp-containing file itself: a Markdown document or a standalone SVG. It neither follows README image references to locate a treestamp nor maintains README-to-SVG relationships. Downloaded/copied SVG can be saved under any user-chosen repository path. Existing repository-relative root semantics apply regardless of that file's directory.

All visual styles must comply with a shared conservative static SVG profile: basic `svg`, grouping, paths/lines, rectangles, and text/tspan geometry; explicit dimensions/viewBox; inline presentation attributes; concrete colors; fixed internal CSS for the adaptive color-scheme media query; and accessible title/description. No scripts, event handlers, animation, `foreignObject`, HTML, external images/styles/fonts, app CSS variables, or dependence on README-specific selectors or CSS variables. Adaptive appearance may follow the embedding element’s standard color-scheme through `prefers-color-scheme`. Encode display text separately from metadata so byte/control/non-XML characters have readable safe labels while metadata preserves identity. Metadata must not be required for the drawing to display.

Typography and wrapping must work in image embedding without app fonts. Start with a portable monospace fallback and conservative measured layout; do not promise identical glyph metrics across clients. Assess long names/notes, wide Unicode, escaped byte names, root-only trees, and both appearance palettes. A font strategy or styling technique that requires unsupported GitHub behavior must be changed or omitted.

This profile is a design constraint, not proof of a finished renderer. Before release, inspect an actual generated artifact embedded in a GitHub README and directly as an image, test the supported browser matrix, and re-load the original repository SVG bytes. A local SVG preview and the Markdown API probe cannot establish end-to-end rendering or metadata retention. Each additional style must pass the same compatibility checks.

## Output selection and file destinations

Choosing an export representation does not change the loaded source path or authorize overwriting it in a different format. Treat input identity/container and selected export format as separate values. The web editor currently copies output and does not write to the repository; SVG download remains a local export. The terminal editor's **Write to document**, and headless maintenance commands, do publish to files and therefore require an explicit container-aware contract.

| Loaded source | Write back to source | Cross-format export |
| --- | --- | --- |
| README or another Markdown document | Replace its managed textual region, preserving unrelated prose and document formatting. | Copy/download/export a standalone SVG; leave the Markdown source and its links unchanged. |
| Standalone SVG treestamp | Replace that SVG artifact using the accepted document and selected supported SVG appearance. | Copy/export a complete textual region for insertion into a README or other Markdown document; leave the SVG source unchanged. |
| Newly created tree | No loaded-document write target, matching today's editor. | Copy/export the chosen representation to an explicitly selected destination. |

A Markdown container may use either supported fenced text style; an SVG container may use any supported graphical style. Switching an export preview to another format must not silently change what **Write to document** writes. The write action should identify the loaded destination/container clearly. Copy/export of another format does not switch the loaded source or reset its dirty baseline. Changing the loaded source remains a deliberate load operation.

Use the source container's preparation/comparison adapter for dirty-state detection, check, update, and write. Retain captured-original comparison, changed-on-disk refusal, atomic replacement, and repository path protections. For Markdown, use the existing managed-region splicing/preservation path. For SVG, prepare a complete regenerated artifact; externally edited drawing markup is not preserved, consistent with metadata authority. A failed write preserves the accepted state and original file. Generic text output may still be used internally as payload but cannot become the publication/comparison path for a loaded SVG.

CLI cross-format export must have an explicit format and destination (or stdout), distinct from updating the loaded source. If a future export action targets an existing Markdown document, use managed-region insertion/update rules and preserve unrelated content; never truncate a README to only the exported region. Reject using the loaded source as the destination of a different container format. The [web/TUI export flow](../planning/svg-export-flow.md) specifies the first-pass controls and replacement interaction. Headless command spelling remains implementation design work; no automatic extension-based conversion is implied.

An SVG export does not insert a Markdown image link, remove an existing text region, or rewrite other documents. Converting a README's presentation to SVG is therefore two deliberate user actions: save the SVG artifact, then replace/insert the README image reference. Converting back means copying the textual treestamp into the Markdown document. Treestamp need not track those relationships or treat that multi-file edit as an application transaction.

## Delivery and acceptance

The [export experience](../planning/svg-export-flow.md) specifies web/TUI controls, clipboard versus file export, source-write behavior, the explicit list-removal policy, and the ordered release plan. Finish the polish release independently; repair filename disambiguation, retire list style, then implement paired SVG support and expose it through both editors. Automatic README linking and optional terminal graphics are follow-ups. This ADR defines the shared format contract rather than duplicating those interaction decisions.

Before implementation, freeze the envelope namespace/schema/version and resource limits, and validate portable typography/wrapping. Those engineering details must satisfy the fixed module and product boundaries above. Test the complete conversion matrix for both remaining text styles and every SVG style, including a minimal second-style test implementation that needs no metadata/editor changes.

Round-trip tests must cover the current document semantics, all node kinds, byte/special paths, subtree hiding, annotations, counts, folds, explicit presentation preferences, and known/unknown graphical styles. Compare canonical decoded document semantics across conversions, not incidental SVG serialization or surrounding README prose. Visible drawing edits cannot change recovered facts; absent, duplicate, contradictory, malformed, oversized, or unsupported payloads fail without replacing the accepted editor state. Verify that no extra hidden data is disclosed.

Rendering tests must verify connected branches and last-sibling endpoints, dimension/wrapping bounds, safe escaping, and the shared GitHub-compatible profile. CLI and hosted output must agree for the same document/appearance. Test source-container writes, cross-format exports, unchanged source identities/baselines, external-file changes, and failure preservation separately. Failed export preserves the accepted session. The paired runtime implementation follows these boundaries; the connected landing illustration remains an independent UI treatment.


## Implemented envelope and limits

The version-1 payload is `{urn:treestamp:svg:1}treestamp`, directly beneath a root SVG `metadata` element. Its required attributes are `version="1"`, `codec="treestamp-text-v1"`, `encoding="base64"`, `text_style`, `show_counts`, `style`, and `theme`. Text style and count preferences are validated against the decoded text; they preserve choices that a root-only tree or a tree without counts cannot reveal. The first graphical style is `continuous`; themes are `adaptive` (the default), `light`, and `dark`. Unknown graphical styles load with an explicit fallback warning; unknown schema/codec versions fail.

Bounds are 1 MiB SVG, 256 KiB decoded textual payload, 10,000 tree rows including root, tree depth 128, XML depth 64, 50,000 XML elements, and namespace URIs of at most 256 characters. Layout caps width at 16,384 pixels and height at 1,000,000 pixels. Annotations stay on the entry baseline with a `#` prefix. Long annotations widen the image up to the existing dimension limit; they are never silently truncated. Display escaping is separate from metadata encoding, so XML-restricted characters and raw Git bytes retain their original identities in the payload. Full-buffer XML parsing rejects a DTD at declaration start, before entities or document content are processed. No incoming drawing is inserted into the web DOM.

`artifacts.py` chooses the container and prepares source writes or separate exports; `svg_metadata.py` owns the envelope, `svg_layout.py` owns layout primitives and the style registry, and `svg.py` combines them. A test-only second style demonstrates reuse of metadata and serialization. The hosted stateless exporter accepts a complete textual region, explicit text preferences, and appearance; it returns generated SVG independently of recovery-state envelopes. Original SVG bytes remain in the source snapshot for dirty/check comparisons; hosted recovery state carries only the compact metadata baseline.

Local Chromium rendering and automated conversion/publication checks are implementation evidence. The maintainer’s GitHub README checks are recorded below; local browser rendering alone does not establish that integration.


## Implementation review

Independently reviewed on 2026-11-24 across metadata parsing, layout, artifact dispatch, atomic publication, controller state, CLI/TUI actions, and hosted integration. Review found and resolved inconsistent dispatch for SVGs with XML comments/processing instructions before the root. A separate frontend review found that regeneration/fallback notices were being dropped; the UI now retains them and browser tests cover the fallback and appearance reset. Small helper extractions kept the new HTTP route out of the existing application factory and separated editor opening messages from source preparation. No blocking implementation finding remained after these changes.

Final local validation passed 1,182 core tests (two skipped) with 99.11% branch-inclusive coverage and 393 hosted tests with 99.13%. The full Chrome browser run passed 263 cases; after the final notice and mobile-scroll refinements, all eight focused SVG cases passed. The 30 pure JavaScript tests passed with 100% coverage of the measured logic module. The initial implementation also received a 60-state responsive sweep; its temporary review log was subsequently retired under the current UI review convention. These automated results did not establish actual GitHub README compatibility; the later maintainer checks below provide that evidence.


## Visual refinement after GitHub rendering check

On 2026-11-24 the maintainer confirmed that the generated assets render in the private `reponomics/treestamp-testing` README and supplied a screenshot. The fixed background panels did not blend into the README, and annotations on separate indented rows obscured the familiar tree notation. The continuous style now has a transparent background, black ink for light appearance and white ink for dark appearance, with reduced opacity for guides and annotations. Notes remain beside their entries with a `#` prefix. These are rendering changes only; the embedded document schema is unchanged. Existing SVGs still load and regenerate with the new presentation.

The web preview supplies a contrasting backdrop matched to the artifact appearance; that backdrop is outside the SVG and is not exported. The test README selects the appropriate asset using GitHub's documented `picture`/`prefers-color-scheme` markup with relative paths. This initial refinement exported one fixed appearance per file; the Adaptive decision below supersedes that default. The app does not create README references.


## Adaptive appearance after cross-browser GitHub checks

On 2026-11-25 the maintainer verified the single-file adaptive experiment in the private `reponomics/treestamp-testing` README in Chrome, Firefox, and Safari. The test uses an ordinary relative Markdown image reference and internal `@media (prefers-color-scheme: dark)` CSS, without a `picture` wrapper or separate theme files. Chrome was explicitly checked with GitHub’s selected appearance differing from the operating system; the maintainer subsequently confirmed Firefox and Safari. This is manual compatibility evidence for those tested browsers, not a guarantee for every renderer or browser version.

Adaptive is now the default for new/text-source SVG exports across web, terminal, and headless interfaces. The version-1 metadata records `theme="adaptive"`; fixed `light` and `dark` values remain valid and retain their exact rendering. Loading an existing fixed-theme SVG must not silently change its appearance. Earlier prerelease readers that accept only light/dark reject the new adaptive value; the textual payload, namespace, and document codec are unchanged.

The renderer supplies black fallback presentation attributes and a fixed internal stylesheet that changes text fill and branch stroke to white in a dark embedding color scheme. It retains transparency, opacity, layout, and editable metadata. No scripts, external styles, user CSS, hosted assets, or account system are required. Incoming styles are still discarded and regenerated from validated metadata. In renderers without media-query support the image falls back to black ink; fixed Light/Dark exports remain explicit alternatives.

The web preview sets the embedding image’s color scheme to match the application theme for Adaptive. Changing the app theme changes only how that same image is displayed; it does not change exported bytes, metadata, or the loaded document’s dirty baseline. Selecting an explicit artifact appearance remains a document change for loaded SVGs. A single download and ordinary README image reference replace the proposed paired-file workflow; automatic README insertion remains outside scope.
