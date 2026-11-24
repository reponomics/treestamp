# Optional local UI review

Use this protocol to inspect visual consistency across application states and viewport sizes. It is optional for contributors. The [shared UI patterns](ui-patterns.md) define the controls, typography, and interaction states to check.

## Capture once, inspect together

Start the [local preview](../web/README.md#run-locally) and install the [browser dependencies](../.github/CONTRIBUTING.md#browser-tests). With the preview running:

```bash
make web-ui-screenshots UI_URL=http://127.0.0.1:8000
```

`UI_REPO` selects a repository available through the preview's GitHub API. Its default, `fixture/repo`, is a request name; it does not create fixture contents. The default `make web-fake` serves this checkout for that name. Source-selection captures require a root `README.md`; note-transfer captures require that README to contain a treestamp with annotated paths absent from the served commit. To serve a separate fixture checkout, run `venv/bin/python web/scripts/fake_github.py --repo /path/to/fixture --port 8100` in place of `make web-fake`. Commit the fixture contents before starting the preview. Missing fixtures are reported as uncaptured states in the manifest.

The command uses isolated browser contexts and writes screenshots, contact sheets, a gallery, and a capture manifest under `output/ui-review/`. `UI_OUTPUT` changes that directory. `UI_BROWSER` selects the browser channel; it defaults to installed Chrome. The gallery covers entry and return screens, source selection, editor tabs and controls, repository information, dialogs, and transfer states at phone, tablet, desktop, and spacious desktop sizes.

Read the manifest for failed or missing captures. Inspect each contact sheet, then open changed or suspicious views at full size. Compare shared controls across views and widths. A successful capture establishes only that an image was produced; record a visual result only after inspecting it.

## Visual checklist

| Check | Look for |
| --- | --- |
| Spacing and alignment | Consistent edges, insets, and grouping; unwanted gaps or crowding |
| Typography | Consistent font, weight, line height, and tree density; readable labels and keyboard hints |
| Color and states | Distinct focus, hover, selection, disabled, and error states; readable text |
| Readability | Clipping, overflow, awkward wrapping, and obscured controls |
| Hierarchy and actions | Visible next actions, clear secondary actions, and controls placed near the content they affect |
| Responsive behavior | Reachable actions and usable tree panes on narrow, short, tablet, and wide layouts |

Screenshots do not establish contrast compliance or keyboard behavior. Check these separately where the change affects them.

## Keep it fast

Allow three minutes for capture, inspection, and recording findings once the preview is ready. Report inspected states and any relevant states left unreviewed. Setup, repairs, and focused verification are separate work.

Fix regressions introduced by the change and recheck the affected views. Triage unrelated findings separately. Repeat a full sweep only after further UI changes; use focused captures to verify a new capture path.

## Maintain the capture coverage

State actions and viewport profiles live in [capture_ui.py](../web/scripts/capture_ui.py). When a new interaction or defect exposes an unrepresented visual state, add it if it presents a distinct layout or presentation risk. Use real UI actions, deterministic fixtures, readiness checks, and a reset when a state could affect the next capture.

Include additions in the manifest, contact sheets, missing-state reporting, and cleanup. Inspect the new state at relevant sizes and verify that the following capture still works. Reuse equivalent states and retire obsolete ones to keep the set small enough to inspect. Timing, focus restoration, or layout movement may also require browser regression tests.

## Temporary findings sheet

Record unresolved findings in the task or review description. A temporary checklist can be used during inspection:

```markdown
Scope: <change under review>
Inspected: <states and viewport sizes>
Not reviewed: <relevant gaps and reasons>

- [ ] <Defect>: <reproduction steps, viewport, and observed behavior>.
  Next action: <fix, decision needed, or issue link>.
```

Remove resolved items. File bugs that remain after the task as issues with reproduction details, and retain their links in the review. Delete the temporary checklist once its findings are resolved or recorded in issues.

## Cleanup

After inspection and triage, run `make web-ui-clean`, passing the same `UI_OUTPUT` if overridden. This removes the gallery's recorded images, contact sheets, HTML, and manifest. Remove additional screenshots created during the review unless they are retained as evidence for a specific issue.
