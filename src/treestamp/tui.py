"""Textual curation against one fixed Git snapshot."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding
from textual.widgets import Label, ListItem, ListView, Static

from treestamp.document import ATTRIBUTION_URL
from treestamp.errors import MarkerError, TreestampError
from treestamp.model import TEXT_STYLES
from treestamp.tui_dialogs import (
    ConfirmScreen,
    PreviewScreen,
    PromptScreen,
)
from treestamp.tui_export import SvgExportScreen
from treestamp.tui_reconcile import PlacementChoiceScreen, ReconcileScreen
from treestamp.tui_rows import Cursor as Cursor
from treestamp.tui_rows import row_label as _row_label
from treestamp.tui_rows import safe_text as _safe_text
from treestamp.tui_rows import tree_prefixes

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from treestamp.editor import EditorController
    from treestamp.session import TreeSession


_HELP = (
    "Edit your tree, then copy or print the complete treestamp.",
    "Stage tree changes before opening with treestamp new or treestamp load.",
    "The captured tree stays fixed for this editing session.",
    "",
    "NAVIGATE",
    "Up / Down       Select an entry",
    "Right           Expand a directory or move to its first child",
    "Left            Collapse a directory or move to its parent",
    "Space           Toggle directory expansion",
    "Home / End      Select the first / last row",
    "Page Up / Down  Move the selection up / down by a page",
    "",
    "EDIT",
    "h               Hide or unhide the selected entry",
    "a               Edit the selected entry's note",
    "S               Unhide all entries",
    "",
    "VIEW AND APPEARANCE",
    "H               Show or conceal hidden entries in the editor",
    "                This does not change which entries are printed.",
    "c               Show or hide counts on collapsed directories",
    "s               Switch between Unicode and ASCII styles",
    "t               Include or remove the Maintained with treestamp trailer",
    "",
    "OUTPUT",
    "v               Preview the printed tree",
    "y               Copy the complete Markdown treestamp",
    "e               Export SVG to a file or clipboard",
    "p               Print the complete treestamp and exit",
    "",
    "?               Show this help",
    "q / Esc         Quit; confirm if there are unwritten changes",
    "",
    "ON DOCUMENT LOAD",
    "If saved paths are gone, choose where their notes belong in the new tree.",
    "One source stays at the top; navigate only the destination tree.",
    "Enter transfers; s skips; u undoes the last transfer decision.",
    "Directories carry matching notes recursively by relative path.",
    "Browsing folders leaves the draft unchanged. Transfer reveals the target.",
    "Transfer ends before editing. Skipped notes are left out.",
    "",
    "Collapsing a folder preserves its curation during this session.",
    "Reopening restores only printed rows and recorded hiding.",
)
STYLES = TEXT_STYLES
STYLE_LABELS = {"unicode": "Unicode", "ascii": "ASCII"}


def _toggle_counts(session: TreeSession) -> str:
    session.show_counts = not session.show_counts
    return (
        "Counts shown on collapsed directories."
        if session.show_counts
        else "Counts hidden."
    )


def _cycle_style(session: TreeSession) -> str:
    style = STYLES[(STYLES.index(session.settings.style) + 1) % len(STYLES)]
    session.settings = replace(session.settings, style=style)
    return f"Printed style: {style}."


def _toggle_attribution(session: TreeSession) -> str:
    enabled = not session.settings.attribution
    session.settings = replace(session.settings, attribution=enabled)
    return (
        "Attribution trailer included." if enabled else "Attribution trailer removed."
    )


class TreestampApp(App[bool]):
    """Edit a TreeSession; Textual widgets never discover or modify project files."""

    TITLE = "treestamp"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "left", "Close / parent"),
        Binding("right", "right", "Open / child"),
        Binding("space", "toggle_fold", "Expand/collapse"),
        Binding("home", "first", "First"),
        Binding("end", "last", "Last"),
        Binding("pageup", "page(-1)", "Page up"),
        Binding("pagedown", "page(1)", "Page down"),
        Binding("h", "hide", "Hide/unhide"),
        Binding("H", "reveal", "Reveal hidden"),
        Binding("S", "show_all", "Unhide all"),
        Binding("a", "annotate", "Note"),
        Binding("c", "counts", "Show counts"),
        Binding("s", "style", "Tree style"),
        Binding("t", "attribution", "Attribution trailer"),
        Binding("v", "preview", "Preview tree"),
        Binding("y", "copy", "Copy Markdown"),
        Binding("e", "svg_export", "Export SVG"),
        Binding("w", "document_write", "Write to document"),
        Binding("q,escape", "quit", "Quit"),
        Binding("p", "print", "Print and exit"),
        Binding("question_mark", "help", "Help"),
    ]
    CSS = """
    Screen { layout: vertical; }
    #title { height: 1; text-style: bold; color: $accent; }
    #tree { height: 1fr; background: $background; }
    #tree ListItem { height: 1; padding: 0; }
    #tree Label { height: 1; text-wrap: nowrap; }
    #tree .hidden-entry Label { text-style: dim; }
    #attribution { height: auto; margin-top: 1; }
    #status, #summary, .controls { height: auto; }
    #status { color: $text-muted; border-top: solid $primary-muted; }
    #summary, .controls { background: $surface; }
    """

    def __init__(self, editor: EditorController) -> None:
        super().__init__()
        self.editor = editor
        self.session = editor.state.session
        self.cursor = Cursor(self.session)
        self.tree_view = ListView(id="tree")
        self.attribution_widget = Static(
            f'Maintained with [link="{ATTRIBUTION_URL}"]treestamp[/link]',
            id="attribution",
        )
        self.attribution_widget.display = False
        self.status_widget = Static("", markup=False, id="status")
        self.summary_widget = Static("", id="summary")
        self.document_controls = Static(
            "Document: w Write to document", markup=False, classes="controls"
        )
        self.document_controls.display = self.editor.state.document_path is not None
        self._rebuilding = False

    def compose(self) -> ComposeResult:
        yield Static(
            _safe_text(f"treestamp · Root: {self.session.settings.root}"),
            markup=False,
            id="title",
        )
        yield self.tree_view
        yield self.attribution_widget
        yield self.status_widget
        yield Static(
            "[bold]Tree[/]     ↑↓ Select  ←→ Expand/collapse  Space Toggle  "
            "h Hide/unhide  a Note",
            classes="controls",
        )
        yield self.summary_widget
        yield self.document_controls
        yield Static(
            "[bold]Output[/]   v Preview  y Copy Markdown  e Export SVG  "
            "p Print & exit    ? Help  q Quit",
            classes="controls",
        )

    async def on_mount(self) -> None:
        status = self.editor.state.status
        if not self.session.root.children:
            status = (
                "No staged files beneath this root. "
                "Stage files with git add and reopen."
            )
        await self.refresh_tree(status)
        self._offer_placement()

    def _set_status(self, text: str) -> None:
        self.status_widget.update(_safe_text(text))

    def _sync_cursor(self) -> None:
        self.cursor.selected = self.tree_view.index or 0
        self.cursor.move(0)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view is not self.tree_view or self._rebuilding:
            return
        previous = self.cursor.selected
        self._sync_cursor()
        if self.cursor.selected != previous:
            self._set_status("Selected: " + (self.cursor.path or "."))

    def _tree_items(self) -> list[ListItem]:
        rows = self.session.visible_rows()
        return [
            ListItem(
                Label(
                    _safe_text(prefix + _row_label(node, self.session)), markup=False
                ),
                classes="hidden-entry" if self.session.is_hidden(node.path) else "",
            )
            for (node, _), prefix in zip(rows, tree_prefixes(rows), strict=True)
        ]

    async def refresh_tree(self, status: str = "") -> None:
        self._rebuilding = True
        self.cursor.move(0)
        selected = self.cursor.selected
        try:
            await self.tree_view.clear()
            await self.tree_view.extend(self._tree_items())
            self.tree_view.index = selected
        finally:
            self._rebuilding = False
        files, dirs = self.session.hidden_stats()
        self.attribution_widget.display = self.session.settings.attribution
        self.document_controls.display = self.editor.state.document_path is not None
        if self.editor.state.document_path is not None:
            relative = self.editor.state.document_path.relative_to(
                self.editor.state.snapshot.repo
            )
            container = self.editor.state.source_format.upper()
            self.document_controls.update(
                f"Document ({container}): {_safe_text(str(relative))} "
                "| w Write to document"
            )
        self.summary_widget.update(
            "[bold]View[/]     "
            f"c Counts: {'on' if self.session.show_counts else 'off'}  "
            f"s Style: {STYLE_LABELS[self.session.settings.style]}  "
            f"t Attribution: {'on' if self.session.settings.attribution else 'off'}  "
            f"H Hidden: {'shown' if self.session.show_hidden else 'concealed'} "
            f"({files + dirs})  S Unhide all"
        )
        self._set_status(status or "Selected: " + (self.cursor.path or "."))
        self.tree_view.focus()

    async def _browse(self, operation: Callable[[], None]) -> None:
        self._sync_cursor()
        before = self.session.collapsed.copy()
        accepted, _ = self._apply_edit(operation)
        if not accepted:
            return
        if self.session.collapsed == before:
            self.tree_view.index = self.cursor.selected
            self._set_status("Selected: " + (self.cursor.path or "."))
            return
        await self.refresh_tree()

    def _apply_edit(self, operation: Callable[[], str | None]) -> tuple[bool, str]:
        selected = self.cursor.selected
        try:
            with self.editor.edit():
                message = operation()
        except (TreestampError, OSError, ValueError) as exc:
            self.cursor.selected = selected
            message = f"Edit rejected; draft retained: {exc}"
            self._set_status(message)
            return False, message
        return True, message or ""

    async def _edit_and_refresh(self, operation: Callable[[], str | None]) -> None:
        accepted, message = self._apply_edit(operation)
        if accepted:
            await self.refresh_tree(message)

    async def action_left(self) -> None:
        await self._browse(self.cursor.left)

    async def action_right(self) -> None:
        await self._browse(self.cursor.right)

    async def action_toggle_fold(self) -> None:
        await self._browse(self.cursor.toggle)

    def _move(self, delta: int) -> None:
        self._sync_cursor()
        self.cursor.move(delta)
        self.tree_view.index = self.cursor.selected
        self._set_status("Selected: " + (self.cursor.path or "."))

    def action_first(self) -> None:
        self._move(-len(self.session.visible_rows()))

    def action_last(self) -> None:
        self._move(len(self.session.visible_rows()))

    def action_page(self, direction: int) -> None:
        self._move(direction * max(1, self.tree_view.size.height - 1))

    async def action_hide(self) -> None:
        self._sync_cursor()
        await self._edit_and_refresh(self.cursor.toggle_hidden)

    async def action_reveal(self) -> None:
        self._sync_cursor()
        await self.refresh_tree(self.cursor.reveal_hidden())

    async def action_show_all(self) -> None:
        self._sync_cursor()
        await self._edit_and_refresh(self.cursor.show_all)

    async def action_counts(self) -> None:
        await self._edit_and_refresh(partial(_toggle_counts, self.session))

    async def action_style(self) -> None:
        await self._edit_and_refresh(partial(_cycle_style, self.session))

    async def action_attribution(self) -> None:
        await self._edit_and_refresh(partial(_toggle_attribution, self.session))

    def action_annotate(self) -> None:
        self._sync_cursor()
        path = self.cursor.path
        self.push_screen(
            PromptScreen("Note", self.session.annotations.get(path, "")),
            partial(self._accept_annotation, path),
        )

    async def _accept_annotation(self, path: str, value: str | None) -> None:
        if value is None:
            self._set_status("Note edit cancelled.")
            return
        accepted, error = self._apply_edit(
            partial(self.session.set_annotation, path, value)
        )
        if not accepted:
            self.push_screen(
                PromptScreen("Note", value, description=error),
                partial(self._accept_annotation, path),
            )
            return
        message = (
            "Note updated in draft." if value.strip() else "Note removed from draft."
        )
        await self.refresh_tree(message)

    def action_preview(self) -> None:
        try:
            text = self.editor.preview()
        except (TreestampError, OSError) as exc:
            self._set_status(f"Cannot preview tree: {exc}")
            return
        self.push_screen(PreviewScreen("Printed tree preview | no file written", text))

    def action_copy(self) -> None:
        """Copy the complete treestamp; a native tool if present, else OSC 52."""
        try:
            text = self.editor.region_text()
        except (TreestampError, OSError) as exc:
            self._set_status(f"Cannot copy treestamp: {exc}")
            return
        try:
            self._set_status(self._copy_text(text, "the treestamp"))
        except (TreestampError, OSError, ValueError) as exc:
            self._set_status(str(exc))

    def _copy_text(self, text: str, label: str) -> str:
        """Report native delivery separately from an unacknowledged OSC 52 request."""
        lines = text.count("\n")
        command = _clipboard_command()
        if command is not None:
            try:
                subprocess.run(  # noqa: S603
                    command, input=text.encode("utf-8"), check=True, timeout=5
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise MarkerError(f"Cannot copy with {command[0]}: {exc}") from exc
            return f"Copied {label} ({lines} lines) with {command[0]}."
        if len(text.encode("utf-8")) > 100_000:
            raise MarkerError(
                "Clipboard output exceeds the 100 KB terminal transport limit"
            )
        self.copy_to_clipboard(text)
        return (
            f"Sent {label} ({lines} lines) to the terminal's clipboard; "
            "paste to confirm your terminal supports it."
        )

    def action_svg_export(self) -> None:
        self.push_screen(
            SvgExportScreen(self.editor, self._copy_text), self._after_export
        )

    def _after_export(self, message: str | None) -> None:
        self._set_status(message or "SVG export cancelled; draft retained.")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "document_write":
            return self.editor.state.document_path is not None
        return True

    def action_help(self) -> None:
        lines = list(_HELP)
        if self.editor.state.document_path is not None:
            index = lines.index("OUTPUT") + 1
            lines.insert(index, "w               Write back to the loaded document")
        self.push_screen(
            PreviewScreen("Keyboard shortcuts", "\n".join(lines), soft_wrap=True)
        )

    def _offer_placement(self) -> None:
        state = self.editor.state.reconciliation
        if state is None or not state.total:
            self.editor.state.reconciliation = None
            return
        self.push_screen(PlacementChoiceScreen(state.total), self._accept_placement)

    async def _accept_placement(self, accepted: bool | None) -> None:
        if accepted:
            self.push_screen(ReconcileScreen(self.editor), self._after_reconcile)
        else:
            await self._after_reconcile(
                "Continued without these notes. w writes the draft."
            )

    async def _after_reconcile(self, status: str | None) -> None:
        # Placement belongs to loading, not the subsequent editing session.
        self.editor.state.reconciliation = None
        await self.refresh_tree(status or "")

    async def action_document_write(self) -> None:
        path = self.editor.state.document_path
        if path is None:
            return
        try:
            destination = str(path.relative_to(self.editor.state.snapshot.repo))
            message = self.editor.write(destination)
        except (TreestampError, OSError, ValueError) as exc:
            self._set_status(f"Write failed: {exc}")
            return
        await self.refresh_tree(message)

    async def action_quit(self) -> None:
        if self.editor.dirty:
            self.push_screen(
                ConfirmScreen("Discard unwritten changes and quit?"), self._confirm_quit
            )
        else:
            self.exit(False)

    def _confirm_quit(self, confirmed: bool | None) -> None:
        if confirmed:
            self.exit(False)
        else:
            self._set_status("Quit cancelled; draft retained.")

    def action_print(self) -> None:
        try:
            self.editor.region_text()
        except (TreestampError, OSError) as exc:
            self._set_status(f"Cannot print tree: {exc}")
            return
        self.exit(True)


def _clipboard_command() -> list[str] | None:
    """A native clipboard writer on PATH, if any; the terminal is the fallback."""
    candidates = (
        [["pbcopy"]]
        if sys.platform == "darwin"
        else [["clip"]]
        if sys.platform.startswith("win")
        else [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]
    )
    for command in candidates:
        if shutil.which(command[0]):
            return command
    return None


def explore(editor: EditorController) -> bool:
    return bool(TreestampApp(editor).run())
