# Quick local UI review

This is a report-only scan before pushing UI changes, not a release gate. Its purpose is to record rough edges while the work is still fresh, without interrupting feature work or making the maintainer discover everything later. Budget **three minutes total**, including setup and logging. Stop at the deadline and record partial coverage.

## Run only when useful

Run for changes to rendered UI, interaction, copy, or backend behavior that changes a user-visible state. Skip documentation-only changes and a candidate already scanned without subsequent UI changes. Inspect the changed surfaces, not the whole application. Existing automated checks remain separate; this scan never triggers a full test suite or a redesign.

The implementing agent supplies the running preview URL, a short list of changed states, and any existing direct links or fixture steps. Start with one representative affected view; add another viewport or theme only when relevant and time permits. Share the captures across reviewers. Use real content and include hover/focus/selection or error states affected by the change. Reuse the running fixture server; do not spend the time box building new infrastructure. If a relevant state cannot be reached quickly, log it as not reviewed.

Record the candidate commit and whether UI changes were uncommitted, plus the viewed URLs/states, viewport sizes, and themes. Captures and any working diff may live under ignored `output/ui-review/`; keep the concise findings in the tracked [rolling log](ui-review-log.md). Captures are evidence, not permanent repository assets.

## Five narrow lenses

Use the installed skills by name, reading their `SKILL.md` when first used. Their system-building advice is adapted to a quick audit of the existing design, not permission to replace it. Treestamp's choices take precedence: utility tone, existing fonts and palette, readable controls, and a 16px UI text floor.

| Lens | Skill | Quick questions |
| --- | --- | --- |
| Typography | `ui-design:typography-scale` | Are changed text and controls using the existing sizes, weights, and line heights? Any undersized, clipped, or accidentally default-styled text? |
| Color and states | `ui-design:color-system` | Are text and controls legible in the sampled themes? Are hover, selection, focus, warning, and disabled states distinguishable? Measure relevant contrast pairs when computed styles are available; don't claim compliance from screenshots alone. Use AA text targets of 4.5:1, or 3:1 for qualifying large text; assess applicable control/state indicators at 3:1. |
| Spacing | `ui-design:spacing-system` | Are related controls grouped, padding/gaps consistent with the existing scale, and the next action visible? Any cramped controls, excessive empty space, or nested scrolling that obstructs the task? |
| Reading width | `ui-design:readable-measure` | Does body copy wrap comfortably, typically around 45–75 characters on wider screens? Any awkwardly narrow descriptions or stretched paragraphs? Short labels, buttons, filenames, and tree rows are not prose-measure targets; don't force them to 65ch. |
| Flow and copy | Product brief and affected flow | Is the next action obvious? Are terms consistent and literal? Check relevant normal, empty, error, and return/recovery states. Does an error recommend something actually possible on that screen? Are action controls styled as controls? |

The first four reviewers can inspect the same fresh screenshots and computed styles. The flow reviewer exercises the actual browser where available. State what each reviewer actually inspected; source reading alone is not visual review. If a skill or requested model is unavailable, report that explicitly and use the applicable checklist above; never pretend to have used it.

## Parallelism without interference

Allocate roughly 45–60 seconds per lens within the overall deadline. Use available reviewers in parallel, then short waves if needed. The model and concurrency depend on the current runtime; do not assume Sonnet or five free slots. A runtime with four total slots including the coordinator can use three reviewers followed by two, if time remains.

Reviewers are read-only and share the same frozen candidate. Prefer shared captures for visual passes. If multiple reviewers interact with the app, give them separate browser contexts with separate localStorage and clean fixture state; never drive the same tab concurrently. Do not mutate a shared fixture repository during review. When isolation is unavailable, use one browser operator. Do not change the UI midway through a scan.

## Return a short result

Give each reviewer this brief:

> Audit only the supplied changed surfaces through your assigned lens. Do not edit files or propose a redesign. Return up to two concrete findings, or “none observed,” with location/state, evidence, impact, and a small suggested correction. Mark untested states and uncertain observations. Return what you have at the deadline; do not expand scope.

The coordinator deduplicates results into the rolling log. Use one sentence per finding: **state → problem → impact**, with a screenshot or reproduction when useful. Separate a verified breakage from a polish suggestion or an untested risk. Zero findings is valid; do not invent improvements to fill a quota.

No automatic fixes, follow-up agent loops, or new issue per finding. Carry open findings forward; do not re-investigate them on every push or mark them fixed because they were not seen this time. Mark resolved only with a checked fix. A later authorized implementation pass can address them in a batch.

If setup fails or time runs out, log **not reviewed** and the reason. It does not block the push under this protocol. Give the user a short summary of new findings and gaps; do not describe partial review as complete QA. Existing test failures and independently applicable safety requirements retain their normal handling.

This is an agent-run convention, not an installed Git hook. It neither initiates nor authorizes remote writes.
