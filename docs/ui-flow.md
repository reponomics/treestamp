# Web UI flow

Decision recorded November 22, 2026. This document describes the web editor's entry flow, its reasoning, and the corresponding terminal source chooser.

## Decision

The first visit begins with a welcome screen and a public GitHub repository field. After the repository is fetched, one tree lets the user choose a starting point. Selecting a directory offers **Create treestamp here**. Selecting a regular file offers **Load treestamp from document**. The editor opens after the selected action succeeds.

**Explore an example** is a deliberate alternative: it opens one curated example directly in the editor, with an example label. It skips repository entry and source selection. The initial screen does not silently load an example or present an unexplained editor behind a modal.

## Why this changed

The previous design deliberately showed a treestamp as quickly as possible by loading a curated repository automatically. A potential user's feedback exposed a weakness in that assumption: the visitor arrived in an unfamiliar repository and had to infer where the displayed tree came from, what it demonstrated, and how to replace it with their own project. The detailed guide was under a separate Info tab. A short introductory sentence helped explain the controls but did not resolve the unfamiliar starting context.

The revised flow asks the user to choose something they understand first, usually their own repository. Browsing it and selecting a folder or document gives the resulting editor a purpose. Those choices also teach the relationship between the source folder, the generated tree, and the document that will receive it.

The product hypothesis is that a small, meaningful choice early in the visit can make the editor easier to understand and more engaging than immediately showing an unfamiliar result. This is a reasoned response to limited qualitative feedback and a promising prototype, not a measured claim about activation or conversion. The example remains an offramp for visitors who want to explore before choosing a repository.

## Arrival rules

| Arrival | Initial experience |
| --- | --- |
| First visit to `/`, without a usable local saved tree | Welcome and repository entry |
| Return to `/` with a saved tree | Attempt to restore that tree directly |
| Bare `/owner/repo` with a matching saved tree | Attempt to restore that tree directly |
| Bare `/owner/repo` without a matching saved tree | Browse that repository's tree |
| Explicit session, commit, or source settings in the URL | Honor the explicit link rather than substitute a locally saved tree |
| **Explore an example** | Open the one curated example directly in the editor |
| Expired or unavailable saved snapshot | Explain the failure and offer a fresh repository load; do not silently replace the captured commit |

The browser stores one current accepted tree. Successful opening of another tree replaces it. Merely browsing or selecting a candidate must not replace the tree, its local record, or its URL. Returning from source selection resumes the accepted editor state. Successful edits renew the server snapshot's one-hour TTL; local storage is convenience for short return visits, not durable backup storage. Saving and restoring stay in the background: the editor does not show routine saved/restored notices or a control for clearing local storage. Unavailable snapshots and other failures still receive actionable explanations.

## Navigation and presentation

The visible sequence is repository entry → folder or document selection → editor. **Back** in source selection returns to repository entry. Once a tree is open, that entry screen is titled **Open another tree**, rather than welcoming the returning user again. **Resume progress** cancels source selection and preserves the current work. The editor's **Open another tree** action starts with the current repository's folders and documents; Back allows choosing a different repository.

The treestamp wordmark opens repository entry within the app. It does not reload `/` and unexpectedly restore a locally saved session. The current editor remains available through **Resume progress**. Automatic restoration applies to arrivals, not to this navigation action.

Repository entry is the place to type a repository address. The editor shows the accepted repository as a compact summary, with repository information and a GitHub link. Instructions and secondary actions use the same typography and controls as the rest of the app, with comfortably readable text and no bare link-style navigation.

The controls and editor use separate responsive transitions. From 1,024px, repository controls and settings occupy a sidebar beside the tree. Between 768px and 1,024px, the controls above the tree split into repository information on the left and settings on the right; the tree uses the full width below. Below 768px, the controls stack and settings open in a sheet. The masthead has its own space requirement: its attribution stays visible down to 640px. Typography does not shrink to compensate for a layout that needs to change.

**Discard changes** restores the start of the editing session after confirmation. That starting point is captured after annotation transfer finishes, including placements and skips. Later changes to notes, hidden entries, folds, and formatting are discarded; annotation transfer does not reopen. A new tree returns to its starting folder layout, and a bundled example returns to its curated starting point. A failed discard preserves the current tree and its locally saved state. Successful discard saves the result through the same silent mechanism as other accepted edits.

The session envelope retains both the initial and current curation, so this behavior survives local draft restoration and shared session links. Annotation-transfer decisions are provisional and their queue is not retained after acceptance. Older session links without an initial curation use the restored tree as their starting point; they cannot recover a historical start that was never stored.

## Folder and document selection

The unified tree exposes both folders and files as meaningful choices. Expansion and selection are separate interactions: a disclosure control expands a directory, while selecting its row changes the action and the selected-item summary. Keyboard navigation visits both kinds of entry in this mode.

Choosing a folder creates a treestamp rooted at that folder. Choosing **Load treestamp from document** reads only the selected file and loads its existing treestamp; browsing does not scan all repository files for markers.

Repository-scoped code search could highlight documents likely to contain markers without fetching every file. It is deferred: its small shared request allowance would make discovery inconsistent during bursts of visitors entering different repositories. The core flow must remain useful without search results, and future discovery should enhance rather than determine which files can be opened.

Creation and loading represent different intentions. An intermediate version treated a plain document as an opportunity to create its first treestamp. That route was rejected because it turned an unsuccessful attempt to recover existing curation into a different task. A user who came to edit existing annotations, folds, and exclusions has not accomplished that intention by creating a new tree.

If the selected document has no treestamp, show a warning such as “No treestamp found in README.md. Choose another document to load.” Keep the document selected and retain the load action. Do not automatically move selection to its parent or offer creation as the normal next step. The user can deliberately select a directory if they decide to create a new tree. Malformed markers, unreadable contents, missing paths, and service failures remain distinct errors with specific guidance.

The web app creates a Markdown block for the user to copy. It does not create a document or write to GitHub. New-tree creation therefore does not require choosing a destination document in advance: the selected folder defines what the tree describes, and the user chooses where to paste the result. Loading a document identifies the existing treestamp to edit.

## Placing notes before editing

After loading a document, notes whose paths disappeared trigger one choice: **Place notes** or **Continue without them**. This is a preparation step before the editor opens, including when arriving through an explicit document link. Creating a new tree and restoring an existing draft bypass it.

The placement view keeps one source item in a separated bar above a single destination tree. The source path and note remain visible while the user navigates the tree with the keyboard or pointer. Enter places the item; S skips it; U reverses the preceding decision. Folder names retain their trailing slash. Left and Right close and open folders, and the selected folder also has an explicit Open/Close button. No second tree or pane switching is needed.

Placing a directory transfers its own note and notes at identical relative paths beneath it, recursively, when entry kinds match. Missing paths and conflicting notes remain queued for individual decisions. Replacing an existing destination note requires a separate confirmation. Undo reverses the whole directory transfer together. Skipped notes are omitted from the updated tree; **Skip remaining and edit** ends the preparation step immediately.

Destination browsing is provisional: opening folders or revealing hidden entries does not change the draft's saved folds or exclusions. Placement reveals the actual destination of a transferred note. The previous accepted draft remains in browser storage until this step finishes. Failed requests leave the last accepted placement decision intact. Once the editor opens, placement cannot be reopened; a fresh document load starts over from the document.

## Checks and future evaluation

Regression checks cover fresh arrivals, opting into the example, explicit-link precedence, tree restoration, keyboard selection, successful and failed source changes, marker-free document warnings, and narrow-screen layouts. Failed requests must preserve the accepted tree. Source paths must retain exact byte identities and significant whitespace.

Future feedback should distinguish whether visitors can identify what the tree represents, complete their first repository selection, and understand the folder/document relationship. Those observations would support or challenge the hypothesis; the implementation alone does not validate it. If the entry step proves obstructive, adjust its choices or the example offramp before assuming that an automatically loaded example is the only alternative.

## Terminal source selection and platform differences

The TUI starts with a visual tree of its current repository on disk. Selecting a folder offers **Create treestamp here**; selecting a regular file offers **Load treestamp from document**. Browsing includes untracked documents, so a newly pasted treestamp can be loaded without typing its path. The editable tree remains a captured Git index; filesystem browsing does not change that source contract. Invalid selections leave the chooser open, and successful document loads pass through optional note placement before editing. Explicit `--load` still bypasses the chooser.

The web and terminal apps share this source-selection model, but their session persistence is intentionally different. Browser local storage preserves an unfinished draft across visits, and **Resume progress** returns to the current accepted tree while browsing another source. The TUI keeps its draft only in the running process; it does not add a separate recovery file or a matching resume action. A loaded document can be written back, and a new tree is copied or printed for insertion into a document.

This first integration keeps the terminal chooser inside its starting repository. The intended later extension is for a selected filesystem path to determine its containing Git repository, allowing another checkout to be selected and reporting paths outside Git clearly. Cross-repository browsing, a terminal return-to-intro action, and terminal reset behavior are deferred rather than made artificial counterparts of browser navigation.
