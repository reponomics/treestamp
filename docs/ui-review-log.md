# UI review log

One rolling record for the [quick local review](ui-review.md). Keep open items until resolved or explicitly accepted; remove resolved history when it stops being useful. Evidence under `output/` is local and may not exist in another checkout, so retain a short reproduction here.

## Latest review

2026-11-23 continuous landing branches and Tree-only Settings, based on `1b796c5`: inspected four contact sheets and full-size desktop/phone Markdown views. Editing Settings are absent from Markdown and Info, with Format and Copy retained. Initial landing captures exposed inherited preformatted whitespace between list rows, breaking the new connectors; the continuity regression tests caught the same problem. Removed that whitespace treatment; the focused recheck inspected desktop dark, phone dark, and tablet light landing views at full size and confirmed continuous branches and no clipping. All 12 landing cases passed after the correction. All 56 sweep states were captured; review was interrupted by SVG design clarification and exceeded the three-minute window. Existing spacious-picker whitespace remains open. Safari, Firefox, and zoom combinations were not reviewed. Review screenshots were removed.

2026-11-23 shared button patterns, candidate after `015f188`: captured all 56 states with the note-transfer fixture in 8.9 seconds. Inspected all four contact sheets, then full-size desktop/phone returning entry, phone editor and placement workspace, tablet note dialog, and spacious light editor. Navbar/hero typography agrees; secondary actions have consistent borders, surfaces, and weight across screens; primary confirmations remain distinct. Phone header and action rows fit, including Resume session and Try example. No new visual regression was identified in those views. Existing spacious-picker whitespace remains open. Safari, Firefox, and zoom combinations were not reviewed. Sweep, inspection, and logging completed within three minutes. A focused follow-up preserved and checked the 44px repository-information target on a touch-enabled desktop; its full-size screenshot showed no clipping. The 240 existing browser cases and eight new button-pattern cases passed across the full run and corrected-test reruns. Screenshots removed after review.

2026-11-23 landing-page first pass: inspected all four contact sheets (320px dark, 768px light, 1280px dark, 1680px light), then full-size phone/desktop/wide welcome and phone expired-draft views. Hero, repository controls, and example action fit the short phone; illustration continues below the fold. The illustration inherited the global code-block border/padding; a scoped reset removed it. A focused follow-up inspected desktop light/dark and 390px dark screenshots, confirming the unboxed treatment and aligned tree branches. Existing spacious-picker whitespace remains open. Placement invitation/workspace were not reached because this fixture has no transferable notes; those views are not visually reviewed. Safari, Firefox, and zoom combinations were not reviewed. Capture and inspection completed within three minutes; the focused follow-up took under a minute. Eight new landing browser cases and 80 existing entry/layout/theme/placement cases passed. Review screenshots were removed.

2026-11-23 release preparation: compared phone, tablet, desktop, and spacious-desktop contact sheets with the pre-change baseline; inspected full-size changed entry, editor, Settings, picker, placement, and restoration-error views. Additional entry/tab hover and long repository-name checks covered the changed chrome. Shortened picker actions to keep the phone footer on one row. No further visual regression was identified within these views; spacious-picker composition remains open below. Safari, Firefox, and exhaustive zoom combinations were not reviewed. Validation included 232 browser tests and seven final layout reruns. Screenshots were removed after review.

## Initial chrome review

2026-11-22, candidate `4ab4670`, clean UI at capture. User requested a review of the whole chrome after reporting oversized source selection and poorly placed repository identities. Reused localhost:54597 and the fixture repository; fresh captures in `output/ui-review/` cover entry, source picker, editor, Settings, and Info at 1280×900 light/dark and 390×667 light.

Three parallel inherited GPT-6 reviewers covered typography + measure, spacing, and color; the coordinator operated the entry → picker and editor → Settings/Info flows. No Sonnet agents were available. The short scan found inconsistent scale/insets between entry and editor, detached picker actions, unstructured repository context, and excessive mobile Info insets. Measured primary-button text contrast: 6.62:1 light / 11.07:1 dark; supporting text on selection: 4.74:1 / 5.77:1. These are sampled pairs, not an accessibility certification.

Coverage is partial: error/recovery, placement/conflict, long names, and exhaustive focus/hover states were not included in this scan. The three-minute target was exceeded because capture initially waited on a hidden desktop Settings button; exact elapsed time was not recorded. No further review waves were started. Implementation is a separate pass explicitly requested by the user.

## Open findings

- **Spacious picker / verified:** On a large window, a short source tree sits in the corner of an oversized panel and its footer actions are far below the content. This needs a deliberate large-screen composition; filling the viewport is not sufficient. Reported in the user's 2026-11-23 02:06 screenshot; no layout change for this finding in the current pass.
- **Mobile source selection / remaining discoverability:** With several top-level folders, files initially sit below the internal tree scroll area. Actions remain visible; discovering lower entries still requires scrolling.

## Resolved in the current candidate

`672f924`: removed the hide-specific Undo functionality; shortened discard confirmation to the requested text; made Skip remaining and edit a button; distinguished selected rows from hover. Checked in desktop/mobile screenshots and 102 relevant browser tests. This does not resolve the open layout and recovery findings above.

## Current implementation pass

Resolved the scale/alignment findings: entry and picker now use the editor's 16px text baseline and page insets; picker rows are 36px on desktop and 44px on phones; selection actions follow their explanation. Repository context uses the same icon, subdued owner, and stronger name in the picker/editor, with matching name styling in example context. Reduced mobile Info padding. Replaced the promotional entry heading/copy with “Open a repository” and a short folder/document explanation.

Checked the result in light/dark desktop and mobile screenshots. Additional browser walkthrough covered long example repository names, note and keyboard-help dialogs, document selection and placement at 320, 390, 768 and 1280px; no console errors or page-width overflow. The document Load button fits the initial viewport at both 320×568 and 390×667. Evidence: `output/ui-review/after/`, including measured action bounds in `metrics.json`. Existing layout/entry/source-selection/theme/Info browser suite: 55 passed; targeted entry/example follow-up after final copy and phone-height changes: 24 passed. This is a polish pass, not exhaustive state or accessibility QA.


## Follow-up: explain note placement

The placement invitation named a symptom without explaining the document/repository mismatch. Both editors now give that context, count notes whose saved paths are absent, and explain the place-or-leave-out choice. User-facing placement and TUI editing terminology uses “notes”; internal annotation names are unchanged. Checked web prompts at 1280×900 and 390×667, and TUI prompts at 80×24 and 60×20, including singular wording. Evidence: `output/note-context/`. Placement browser tests passed (21); core/TUI tests passed after updating an old error-copy assertion (98 cases). This copy fix does not resolve the remaining short-height placement layout finding.


## Follow-up: selected-row actions above the tree

Moved Note and Hide/Unhide from individual rows into a shared toolbar joined to the tree. A persistent selected-path label and matching accent edge on the row identify the target even while a toolbar button has focus; button descriptions also reference the selected path. Removed the duplicate Example banner and no-document “treestamp” caption. Loaded document names now sit in repository context. The toolbar stays above the tree, and tree text has no overlaid actions.

Visually checked 1280px light/dark, 390px dark and 320px light; checked scrolling at 390px and 768px. Evidence: `output/row-toolbar/`. Browser regression coverage: 209 existing cases plus two new queued-target cases across a full run and focused reruns. The first run identified an extra document-caption row and a stale tab-order assertion; both were corrected and checked. Verified note-dialog focus, selection after hiding/folding, and queued actions retaining the clicked target when selection changes. Independent code/complexity review completed; this is task-specific verification, not a new five-lens scan. Previously open recovery and short-height placement findings remain open.


## Mobile correction: reserve the viewport for the tree

The first toolbar pass left the example tree at about one third of a 390×844 screen. Reduced mobile chrome buttons to 36px, collapsed repository actions into labeled icon controls on one line, and show the repository name without repeating its owner in the visible mobile header; full identity remains accessible and is shown in Repository information. Removed masthead/tab wrapping at narrow widths. Phones now use a fixed-height workspace with an internally scrolling tree, so a short tree does not leave unused space below its pane. The selected-path toolbar remains visible; tablet page scrolling still uses the sticky toolbar with measured keyboard scroll clearance.

Measured example pane: 603px / 844px (71%) at 390px wide, and 327px / 568px (58%) at 320px wide. Added regression contracts for more than half the viewport, viewport containment, accessible icon actions, internal scroll stability and Home selection visibility. The focused mobile/layout/editing/modal checks cover 98 passing cases across targeted runs; prior broader browser coverage is retained. Screenshot evidence in `output/row-toolbar/` was refreshed. This corrects the earlier mobile proportion finding for the editor; remaining source-selection/recovery/placement findings above are separate.

## Tree-first picker and tablet correction

Removed the picker's question heading, repeated selected path, folder/document label, description, and replacement warning. Two short instructions now lead directly to the tree: “New tree — Select folder (root)” and “Load tree — Select file.” The New tree / Load tree action shares the footer with Resume progress. The tree scrolls internally and fills the available height at every width. Removed the now-unused replacement-warning state.

Tablet editing now uses the compact stacked workspace and Settings popover through 1023px, replacing the large settings panel and its divider. Repository actions, view controls, and selected-row actions occupy three rows beneath the masthead. The selected path is no longer printed above the tree; the selected-row highlight, matching action marker, and accessible path descriptions remain. Existing palette and 16px IBM Plex type are retained.

Measured tree panes: editor 807px / 1024px (79%) at 768×1024 and 483px / 700px (69%) at 900×700; picker 348px / 568px (61%) at 320×568. Screenshots: `output/tree-first/`, covering 320, 390, 768, 900, and 1280px in light/dark themes. Independent GPT-6 screenshot/diff review found no material issue within this scope; a separate code review confirmed the warning-state removal has no other behavioral effect. This is a task-specific review, not a fresh five-lens pre-push scan. Safari and browser zoom were not independently checked.

125 targeted browser cases passed: 47 picker/layout/keyboard/focus and 78 editing/reload/draft/placement. New contracts verify tree area, internal scrolling, and both footer actions remaining visible on the same line even with a long source tree. Existing open recovery and short-height placement findings remain; source-file discovery on very short screens still requires tree scrolling.

## Picker tree consistency

The source picker had separate 36px desktop / 44px phone rows, a narrower indentation step, and dot placeholders for files. Replaced those with the editor's shared 32px row rhythm, 16px IBM Plex Mono, four-character indentation, folder weight, and continuous branch guides. Both views now use the same guide-rendering helpers. Removed file dots; a compact 24px disclosure button follows folders that have children, because expanding a folder must remain independent of selecting it as the new root.

Screenshots in `output/picker-density/` compare both views at 390, 768, and 1280px, with measured 32px rows throughout. Independent code review checked sibling/ancestor branch endings and the unchanged selection/toggle behavior. 61 focused browser cases passed, including touch input, matched density/indentation, disclosure independence, branch continuity, picker flows, responsive layout, and editor row interactions. The earlier open recovery and short-height placement findings remain outside this change.

## Note dialog alignment

Removed the duplicate visible Note label while retaining the input's accessible label. Grouped the heading and path on a shared baseline, with long paths wrapping to their own full-width line. Keyboard shortcuts and Cancel/Apply now share a compact footer, wrapping cleanly on phones. Checked light/dark screenshots and long paths at 320, 390, and 1280px in `output/note-polish/`; input naming, focus, Escape, and action visibility were checked manually. Seven existing focused dialog/mobile checks passed. No editing behavior changed.

The note-dialog context was still too verbose: replaced the full path with only the selected file/folder name. Long names stay on one line with ellipsis. The prior long-path wrapping treatment is superseded; full paths are not displayed in this dialog.

## Repeatable screenshot sweep

Added the agent-operated pre-commit gallery and checklist. The first run against the local fixture preview captured 13 states across three profiles (39 screenshots) in 5.8 seconds with no browser errors. Inspected all three contact sheets, then full-size returning entry, tablet settings, and phone transfer invitation. The visible entry imbalance and transfer clipping are recorded above; the previously recorded short-height transfer-work overflow is also obvious in the phone sheet. Capture success does not resolve these findings. Keyboard/a11y behavior, alternate data sets, every theme/width combination, and unavailable-snapshot recovery are not covered by this quick visual pass. Artifacts: `output/ui-sweep/`; manifest records the candidate and dirty working tree.

## Addressed gallery findings and picker interaction

Simplified entry to a repository input with a compact Browse action and a quiet Resume progress / Example tree footer. Removed redundant introductory text. Settings now has one column with Discard changes beneath the options. The transfer invitation wraps actions rather than clipping them; the transfer workspace keeps its footer outside scrollable content, so decisions remain visible on short phones. Its tree shares the editor/picker branch geometry and 32px rows. Visible transfer context uses the source name without a repeated full path.

Removed source-picker arrow buttons at the user's request: folder rows select and toggle on click, Enter, or Space; files select on activation, and keyboard arrow browsing remains available. Updated the screenshot script to use row activation and added unavailable-draft recovery. The latter now recommends reopening the repository without suggesting copying a nonexistent tree; the opening control retains its visible label on phones in that state.

83 affected browser cases passed, with seven transfer checks rerun after the final sizing change. The later entry/recovery pass passed 19 cases (including overlapping entry checks). Reviewed the phone, tablet, desktop, and newly added spacious-desktop contact sheets, plus full-size changed entry, settings, transfer, and recovery views; final captures are in `output/ui-review/`. Sparse-tree whitespace in a spacious window remains open, and the checklist now explicitly checks emptiness as well as crowding. CONTRIBUTING was not changed in this pass.
