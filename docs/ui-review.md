# Agent visual review protocol

Before committing web UI changes, capture the standard views and **look at the resulting images**. The purpose is to catch obvious drift across screens while the work is local. Passing tests or generating screenshots is not a visual review.

## Capture once, inspect together

With the local preview running:

```bash
make web-ui-screenshots UI_URL=http://127.0.0.1:8000
```

Use the fixture repository (`fixture/repo`) for repeatable source selection and note transfer. Override `UI_REPO` for another local fixture. The command writes a gallery, full-size screenshots, contact sheets, and a capture manifest under ignored `output/ui-review/`; `UI_OUTPUT` changes that directory. It uses isolated browser sessions, leaving the user's browser and draft alone.

The sweep visits entry and return screens, folder/file selection, the editor and its secondary views, dialogs, and transfer states at phone, tablet, desktop, and spacious desktop sizes. Consult the manifest for what actually ran. A missing transfer fixture or failed capture is **not reviewed**, never a pass. Screenshots show the viewport rather than expanding the page to conceal overflow.

Start with the contact sheets to spot differences between views. Open the full-size images of changed components and anything suspicious. Compare the same component across widths and screens, including neighboring screens that were not edited. Use one reviewer by default; extra agents are optional and should share these images rather than each repeating setup.

Keep images only while reviewing. After recording findings in the rolling log, run `make web-ui-clean` before committing or handing back the task (with the same `UI_OUTPUT` if overridden). The command deletes the gallery's recorded screenshots, contact sheets, HTML, and manifest, leaving unrelated files alone. Remove additional task-generated screenshot folders as well; keep artifacts only if the user asks. This cleanup is part of the agent's task, not the contributor's responsibility. There is no background timer: an interrupted task can leave artifacts behind, so the next capture also removes the previous gallery before starting. Use the standard output directory rather than creating archives.

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

The typography, color, spacing, and measure checks draw on the `ui-design:typography-scale`, `ui-design:color-system`, `ui-design:spacing-system`, and `ui-design:readable-measure` skills. Use these as review lenses for the existing utility, not as a reason to redesign its type or palette.

## Keep it fast and honest

Budget three minutes for capture, inspection, and a short entry in the [rolling log](ui-review-log.md). Record the candidate, images actually inspected, findings, and gaps. One line per finding is enough: **view → visible problem → consequence**. No numerical design score or visual-coverage percentage.

Fix obvious regressions introduced by the current change and recheck that view; log unrelated polish work without starting a repair loop. Keep unresolved findings visible. If capture or inspection cannot finish within the budget, report partial review and the reason rather than claiming everything looks good. Skip a repeat sweep when the UI has not changed since the last inspected capture.

This is a local review convention, not a Git hook, pixel-diff gate, test-suite replacement, or authorization to push.
