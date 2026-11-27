# Shared web UI patterns

The web app uses native HTML controls and shared CSS rather than a component framework. Reuse the patterns below across the landing page, repository picker, editor, and dialogs. The forest palette and IBM Plex typefaces are defined in `web/src/treestamp_web/static/style.css`.

## Action buttons

`web/src/treestamp_web/static/buttons.css` owns action-button typography, surfaces, borders, corners, and enabled, hover, disabled states. The shared focus ring is defined with the other focusable controls in `style.css`.

| Pattern | Markup | Use |
| --- | --- | --- |
| Secondary | `<button type="button">…</button>` | Navigation, alternative actions, repeated editor tools, Cancel, Close, and Resume session. Always has a visible surface and border. |
| Primary | `<button class="primary" type="button">…</button>` | The next step or confirmation: Create, the selected source action, Apply, and Transfer here. On the landing page, Create is the repository field's action and Pick a file or folder… is the secondary alternative. Uses the accent fill when enabled. |
| Navigation link styled as a button | `<a class="button-link" href="https://github.com/reponomics/treestamp">GitHub</a>` | Navigation such as visiting GitHub. Shares the secondary button's appearance and hover/focus treatment; retains native link semantics. |
| Icon-only action | A secondary button or button link with an icon and an accessible name | Same appearance as its text equivalent. A view may make it square or visually hide its label where space is constrained. |

Button prominence and submission behavior are independent: use `type="submit"` for form submission and `type="button"` for other actions.

Use the native `disabled` attribute for unavailable button actions. Disabled primary buttons use the same disabled treatment as other buttons. Do not imitate a disabled control by changing its opacity, and do not make an anchor look disabled when it can still navigate.

Views may adjust placement, width, spacing, and compact control dimensions to fit their layout. They must not assign independent background, border, font-weight, corner, or hover recipes to ordinary actions. Secondary actions remain visibly button-like at every breakpoint. Introduce a new shared variant only when a distinct interaction role requires it; do not create a variant for one screen or one action.

Copy is a repeated editor action and uses the secondary treatment. Its temporary success label and green border communicate confirmation. The TUI-mode pressed appearance communicates a toggle that stays enabled until switched off in the current page; it is not persisted across page loads. These state treatments do not create separate button families. The theme switch describes its next action in its label and keeps the secondary treatment in both themes.

## Controls with different semantics

Tabs use an underline and `aria-selected` to identify the active panel. Tree disclosures use compact branch-aligned controls and `aria-expanded`. Selectable rows use the shared selection treatment. Preserve those patterns instead of making them look like ordinary action buttons.

## Brand typography

Apply `.brand-wordmark` to the treestamp name in the navbar and landing hero. It owns IBM Plex Sans, semibold weight, and letter spacing. Each layout controls its own size and margins. Directory trees and the landing illustration use IBM Plex Mono. The Reponomics wordmark retains its separate brand typeface.

## Checking changes

Compare controls with the same role across views and in both themes, including hover, keyboard focus, and disabled states. Browser tests compare their computed appearance without hard-coding palette values. The [optional local visual-review protocol](ui-review.md) provides a repeatable way to inspect spacing, action hierarchy, and responsive layout.
