# Optional local UI review

This is the visual-review protocol the maintainer uses locally. It is available for contributors to adopt or adapt, but it is not a contribution requirement or a mandatory step before every commit. Follow it manually or ask an agent to use it; this document does not configure automatic invocation, and no project skill is required.

The purpose is to catch obvious drift across screens while a change is local. Capture representative states and **look at the resulting images**. Passing tests or generating screenshots is not a visual review.

## Capture once, inspect together

Use the existing [local preview setup](../web/README.md#run-locally) and [browser dependencies](testing.md#suites-and-commands). With the preview running:

```bash
make web-ui-screenshots UI_URL=http://127.0.0.1:8000
```

Use the fixture repository (`fixture/repo`) for repeatable source selection and note transfer. Override `UI_REPO` for another local fixture. The command writes a gallery, full-size screenshots, contact sheets, and a capture manifest under ignored `output/ui-review/`; `UI_OUTPUT` changes that directory. It launches isolated browser sessions and captures application pages, not the desktop or other applications. The existing browser session and draft are left alone.

The sweep visits entry and return screens, folder/file selection, the editor and its secondary views, the repository-info hover, dialogs, and transfer states at phone, tablet, desktop, and spacious desktop sizes. Consult the manifest for what actually ran. A missing transfer fixture or failed capture is **not reviewed**, never a pass. Screenshots show the viewport rather than expanding the page to conceal overflow.

Start with the contact sheets to spot differences between views. Open the full-size images of changed components and anything suspicious. Compare the same component across widths and screens, including neighboring screens that were not edited. Use one reviewer by default; extra agents are optional and should share these images rather than each repeating setup.

Keep images only while reviewing. After triaging findings, run `make web-ui-clean` (with the same `UI_OUTPUT` if overridden). The command deletes the gallery's recorded screenshots, contact sheets, HTML, and manifest, leaving unrelated files alone. Remove additional review screenshots as well, unless intentionally retaining evidence for a specific issue or review. When an agent runs the sweep, cleanup is part of that task. There is no background timer: an interrupted task can leave artifacts behind, so the next capture also removes the previous gallery before starting. Use the standard output directory rather than creating archives.

## Visual checklist

| Check | Look for |
| --- | --- |
| Spacing and alignment | Shared edges and baselines; related items grouped; consistent insets; no stray labels, oversized gaps, or off-center dividers. |
| Typography | Consistent size, weight, line height, and tree density across views; no accidental browser-default styling or oversized utility labels. Keep the existing 16px UI text baseline. |
| Color and states | Existing palette and semantic roles; readable text; distinct focus, hover, selection, disabled, and error states. Screenshots alone do not establish contrast compliance. |
| Readability | Clipped input values, awkward wrapping, repeated labels, unnecessary instructions. Prefer an item name to a full path for context. Reserve prose measure rules for prose, not trees or short controls. |
| Balance | Check both crowding and excessive emptiness. The tree owns the editor, but a small tree should not feel stranded in an enormous panel. Use available space deliberately; avoid oversized gaps, distant actions, and controls that squeeze useful content. Check spacious desktop windows as well as phones. |
| Hierarchy and actions | One clear next action; secondary actions quieter and sensibly placed; buttons no larger than their job requires; keyboard hints do not crowd mobile layouts. |
| Consistency and responsive behavior | Shared components look related across entry, picker, editor, and dialogs. Check short-height phones, tablet transitions, long names, and dense trees. Primary actions remain reachable. |

Use the [shared UI patterns](ui-patterns.md) as the reference for the existing utility; a sweep is not a request to redesign its type or palette.

## Keep it fast and honest

Budget three minutes for capture, initial inspection, and recording actionable findings once the preview is ready. Preview setup, implementation, repairs, and focused verification are separate work. If the scan reaches the budget, report what was inspected and what remains unreviewed. Do not claim that generating a complete gallery means every view passed. No numerical design score or visual-coverage percentage is needed.

Fix obvious regressions introduced by the current change through the normal implementation workflow, then recheck the affected views. Triage unrelated polish separately so the scan does not become an automatic repair loop. Skip a repeat sweep when the UI has not changed since the last inspection; validate a new capture path with a focused check instead.

## Maintain the capture coverage

The state actions and viewport profiles live in [the capture script](../web/scripts/capture_ui.py). If a new interaction or discovered defect requires a one-off screenshot, check whether its state belongs in the recurring suite. Add distinct presentation risks to that inventory, using real UI actions, deterministic fixtures, readiness checks, and a reset when the state could affect the next capture. Include new captures in the manifest, gallery/contact sheets, missing-state reporting, and cleanup. Inspect the addition at relevant sizes and verify the following capture still works.

Keep the matrix small enough to inspect. Reuse equivalent states, retire obsolete ones, and avoid multiplying every case by every possible theme or viewport. Temporal or functional problems, such as layout movement after an edit or focus restoration, may also need a browser regression test. A one-off image is diagnostic evidence, not an expansion of recurring coverage. If a fixture is missing or an addition is deferred, identify the gap and its next action explicitly.

## Temporary findings sheet

There is no committed review log. Use a temporary sheet only when a scan produces unresolved findings or meaningful coverage gaps. For local work, `output/ui-review-findings.md` is already ignored and sits outside the gallery directory, so `make web-ui-clean` does not delete it. Start from the template below rather than appending to earlier scan history.

```markdown
# UI findings for this task

Scope: <change or task being reviewed>
Inspected: <states and profiles actually inspected>
Not reviewed: <relevant gaps and reasons, or none>

- [ ] <UI defect or coverage gap>: <state, fixture/actions, and viewport> → <visible consequence or missing coverage>.
  Next action: <fix in this task, specific decision needed, or recorded follow-up>.
```

Keep only actionable unfinished items. Remove verified fixes and explicitly accepted findings; do not accumulate successful checks, test counts, completed-work narratives, or dated scan entries. If nothing remains to triage, delete the sheet. A clean scan needs only a short summary in the current review or task response.

At the end of the task, move confirmed bugs and durable design work into the project's normal issue or planning process, with enough detail to reproduce or evaluate them. The sheet is not a second backlog. Do not discard unresolved findings just to start fresh: retain any item awaiting a decision until its disposition or handoff is actually recorded. The next session should use a fresh sheet after that triage, without carrying forward historical scan notes.

This is a local review convention, not a Git hook, pixel-diff gate, test-suite replacement, or authorization to push.
