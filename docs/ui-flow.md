# Web UI flow

The web editor's entry flow is repository entry → source selection → editing. Source selection identifies either the folder a new treestamp describes or the document containing an existing treestamp. The web editor exports Markdown for the user to copy into documentation; it does not write files or commit to GitHub.

## Arrivals and navigation

| Arrival | Initial experience |
| --- | --- |
| First visit to `/` | Repository entry |
| Return to `/` with a saved session | Repository entry with **Resume session** |
| Bare `/owner/repo` | Source selection for that repository, with **Resume session** when a matching saved session exists |
| Explicit session, commit, or source settings in the URL | Open the specified session or source |
| **Try example** | Open a curated, bundled snapshot of reponomics/treestamp |

**Open a tree** and the treestamp wordmark open repository entry. The folder control, **New or load treestamp**, opens source selection within the current repository. **Back** returns from source selection to repository entry. **Resume session** returns to the accepted editor state or restores the saved session after a return visit.

Browsing candidates preserves the accepted treestamp, its saved record, and its URL. Successfully opening a new source replaces the accepted session. Controls remain available at every viewport size: repository controls and settings occupy a sidebar on desktop; narrower layouts use a compact repository bar and a settings sheet.

## Editing and export views

**Tree** owns editing controls, including notes, hiding, reveal-hidden, Unhide all, and Settings. Leaving Tree closes an open Settings sheet and hides its desktop sidebar section. **Markdown** previews the exported plaintext, lets the user choose its text format, and provides Copy treestamp. Returning to Tree restores editing controls without resetting curation. **Info** also hides editing Settings.

## Source selection

Activating a folder row selects it and toggles its expansion. **Create** starts a treestamp rooted at the selected folder. Activating a file selects it; **Load** reads its existing treestamp. Left and Right provide keyboard expansion and navigation without changing the selected source. Source paths retain exact byte identities and significant whitespace.

Browsing does not inspect every file for treestamp markers. If a selected document has no treestamp, the chooser explains the problem and keeps that file selected so the user can choose another. Malformed markers, unreadable contents, missing paths, and service failures retain the current work and provide recovery guidance.

## Saved sessions

The browser stores one accepted session locally. Saving happens after successful opening or editing; returning visitors explicitly choose **Resume session** to restore it. Explicit session URLs take precedence over local storage. Storage failures do not prevent editing.

Restoration requires the captured server snapshot. If that snapshot is unavailable, the entry screen retains the saved session and offers repository browsing to start fresh. The service does not substitute a different commit into a saved session. Snapshot retention and cache behavior are documented in [Design](design.md#hosted-editor); local storage supports short return visits, not durable backup storage.

## Placing notes before editing

Loading a document whose annotated paths disappeared offers **Place notes** or **Continue without them** before editing begins. Creating a treestamp and resuming a saved session bypass this step.

The placement view keeps one source name and note above the destination tree. Enter places the note, S skips it, and U reverses the preceding decision. Left and Right close and open folders; the selected folder also has an Open/Close control.

Placing a directory transfers notes at identical relative paths beneath it recursively when entry kinds match. Missing paths and conflicting notes remain queued. Replacing an existing destination note requires confirmation. Undo reverses the whole directory transfer together. **Skip remaining and edit** completes preparation with the unplaced notes omitted.

Destination browsing is provisional: opening folders or revealing hidden entries does not change saved folds or exclusions. Placement reveals the actual destination of a transferred note. The previous accepted session remains in browser storage until preparation finishes. Failed requests preserve the last accepted placement decision. A fresh document load starts placement again from the document.

## Discard changes

**Discard changes** restores the accepted starting point after confirmation. That baseline is captured after note placement, including placements and skips. Later edits to notes, hidden entries, folds, and formatting are discarded. New treestamps return to their starting folder layout; examples return to their curated starting point.

The session envelope retains both initial and current curation, so the baseline survives saved-session restoration and shared links. Sessions without initial curation adopt their restored curation as the baseline. A failed discard preserves the current treestamp and its saved state.

## Terminal behavior

The terminal editor uses a visual source chooser within its starting repository. It includes untracked documents for loading, while the editable treestamp comes from a captured Git index. Explicit `--load` bypasses the chooser. Terminal drafts live in the running process; persistence comes from writing a loaded document or copying a new treestamp into documentation. See the [CLI reference](cli-reference.md#interactive-editor) for commands, keyboard controls, and placement behavior.
