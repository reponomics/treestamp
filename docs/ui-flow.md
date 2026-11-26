# Web UI flow

The web editor opens repository-root treestamps directly from the landing page. Source selection is available for other folders or documents. The web editor copies Markdown or downloads/copies a standalone SVG. It does not write repository files or commit to GitHub.

## Arrivals and navigation

| Arrival | Initial experience |
| --- | --- |
| First visit to `/` | Repository entry |
| Return to `/` with a cached draft | Repository entry with **Resume session** |
| Bare `/owner/repo` | Source selection for that repository |
| Explicit session, commit, or source settings in the URL | Attempt to open the specified session or source |
| **Open this example** | Open a curated, bundled snapshot of reponomics/treestamp, previewed on the landing page |

The treestamp wordmark returns to repository entry; the editor has no separate new-source controls. Returning to the landing page preserves current work for **Resume session** with an empty repository field, and changes the address to `/`, so reloading the landing page does not reopen the session; resuming restores the session's address. **Create**, inside the repository field, opens a fresh tree at the repository root without reading a document. **Pick a file or folder…** opens source selection, where a document such as `README.md` loads its existing treestamp. Pressing Enter in the repository input defaults to Create. Progress and failures appear in place of the field's label, so the controls do not move. **Back** returns from source selection to repository entry. **Resume session** is available only on repository entry and returns to the accepted editor state or attempts to restore the cached draft after a short return visit.

Root README validation happens in the load request while the landing page remains visible. A missing README, absent or malformed treestamp, or service error appears inline and retains the entered repository and previous session. All entry actions are disabled while a request is pending.

Browsing candidates preserves the accepted treestamp, its cached record, and its URL. Successfully opening a new source replaces the accepted session. Controls remain available at every viewport size: repository controls and settings occupy a sidebar on desktop; narrower layouts use a compact repository bar and a settings sheet.

## Editing and export views

**Tree** contains editing controls and Settings. **Export** offers Markdown source or an SVG image independently of the loaded format. Markdown uses Unicode or ASCII branches; SVG can be downloaded or copied as complete, editable source. Export starts with Markdown selected. Selecting SVG prepares its preview; leaving Export resets the view and cancels pending preparation while preserving edits.

New SVG exports use **Adaptive** appearance, adapting one transparent image to light and dark color schemes. **Light** and **Dark** provide fixed overrides; loaded SVGs retain their saved appearance. One request prepares all three appearances, so switching between them is immediate. Temporary server contention keeps preparation pending for up to 30 seconds, then offers Try again. Users save the SVG in their repository and reference it from their README. Loading that file reopens its embedded treestamp for editing. See [Document format](design.md#svg-artifacts) for the metadata and regeneration contract.

## Source selection

Two stacked instructions explain creating a new treestamp from a folder and loading an existing treestamp from a file. Activating a folder row selects it and toggles its expansion. **Create** starts a treestamp rooted at the selected folder. Activating a file selects it; **Load** reads its existing treestamp. Both actions remain visible with stable labels: only Create is enabled for a folder, and only Load for a file. Both are disabled while loading or opening a selection. There is no Resume session action in this screen; Back leads to repository entry where recent work can be resumed. Left and Right provide keyboard expansion and navigation without changing the selected source. Source paths retain exact byte identities and significant whitespace.

Browsing does not inspect every file for treestamp markers. If a selected document has no treestamp, the chooser explains the problem and keeps that file selected so the user can choose another. Malformed markers, unreadable contents, missing paths, and service failures retain the current work and provide recovery guidance.

## Returning to recent work

The browser caches one accepted draft after successful opening or editing. **Resume session** is a best-effort convenience for short return visits, not a save or backup feature. Storage failures do not prevent editing, and returning later is not guaranteed to recover the draft. Users keep their work by copying Markdown or downloading an SVG.

Repository draft restoration requires the captured server snapshot. If that snapshot is unavailable, the entry screen retains the cached draft and offers repository browsing to start fresh; it does not silently substitute another commit. Unmodified bundled examples can be restored from their included data without the server snapshot; edited examples require the captured server snapshot. Snapshot retention and cache behavior are documented in [Design](design.md#hosted-editor).

The address can also encode editing state, and explicit address state takes precedence over the local cache. This is implementation behavior, not a durable session-sharing workflow; users are not expected to save URLs to preserve their work.

## Transferring notes on load

Loading a document whose annotated paths disappeared opens one **Transfer notes** modal over the prepared editor in Tree view. The modal immediately shows the source note and destination tree; there is no separate invitation or preparation page. Creating a treestamp and resuming recent work bypass this step.

The modal keeps one source name and note above the destination tree. **Transfer here** (Enter) transfers the note, **Skip note** (S) leaves it out, and **Undo** (U) reverses the preceding decision. Left and Right close and open folders; the selected folder also has an Open/Close control. Notes are processed sequentially.

Transferring a directory carries notes at identical relative paths beneath it recursively when entry kinds match. Missing paths and conflicting notes remain queued. Replacing an existing destination note requires confirmation. Undo reverses the whole directory transfer together. **Continue without remaining notes** finishes with unresolved notes omitted; Escape has the same effect when no request is pending. Resolving the final note completes the modal automatically.

The editor behind the modal presents the initial incoming tree, but does not accept it yet. Destination browsing is provisional: opening folders or revealing hidden entries does not change saved folds or exclusions. Transfer reveals the actual destination of a transferred note. The previous accepted session, URL, and browser record remain intact until the modal finishes. Failed requests preserve the last accepted transfer decision. Cancelling or superseding the load restores the preceding presentation. A fresh document load starts transfer again from the document.

## Discard changes

**Discard changes** restores the accepted starting point after confirmation. That baseline is captured after note transfer, including transfers and skips. Later edits to notes, hidden entries, folds, and formatting are discarded. New treestamps return to their starting folder layout; examples return to their curated starting point.

The session envelope retains both initial and current curation, so a successfully restored cached draft retains its discard baseline. Older state without initial curation adopts its restored curation as the baseline. A failed discard preserves the current treestamp and its cached state.

Terminal interactions are documented in the [CLI reference](cli-reference.md#interactive-editor).
