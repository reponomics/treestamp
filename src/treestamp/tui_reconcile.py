"""Place one removed annotation at a time using a single destination tree."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Rule, Static

from treestamp.errors import TreestampError
from treestamp.session import TreeSession
from treestamp.tui_dialogs import ConfirmScreen, PreviewScreen
from treestamp.tui_rows import Cursor, row_label, safe_text, tree_prefixes

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from treestamp.editor import EditorController
    from treestamp.model import Node


class PlacementChoiceScreen(ModalScreen[bool]):
    """Offer placement once, before editing a newly loaded draft."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter,y,Y", "place", "Place annotations", priority=True),
        Binding("escape,n,N", "skip", "Continue without them", priority=True),
    ]
    DEFAULT_CSS = """
    PlacementChoiceScreen { align: center middle; }
    #placement-choice { width: 90%; max-width: 70; height: auto; padding: 1 2;
                        border: round $accent; background: $surface; }
    #placement-choice Static { height: auto; }
    #placement-choice-title { text-style: bold; margin-bottom: 1; }
    #placement-choice-keys { margin-top: 1; }
    """

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        noun = (
            "annotation lost its place"
            if self.count == 1
            else "annotations lost their place"
        )
        pronoun = "it" if self.count == 1 else "them"
        with Vertical(id="placement-choice"):
            yield Static(
                f"{self.count} {noun}.", markup=False, id="placement-choice-title"
            )
            yield Static(f"Place {pronoun} in the updated tree?", markup=False)
            yield Static(
                f"Enter Place annotations\nEsc Continue without {pronoun}",
                markup=False,
                id="placement-choice-keys",
            )

    def action_place(self) -> None:
        self.dismiss(True)

    def action_skip(self) -> None:
        self.dismiss(False)


class PlacementConfirmScreen(ConfirmScreen):
    """Keep replacement decisions reachable even for long paths and annotations."""

    DEFAULT_CSS = """
    PlacementConfirmScreen .confirm-panel { max-height: 90%; }
    PlacementConfirmScreen VerticalScroll { height: auto; max-height: 1fr; }
    PlacementConfirmScreen #confirmation { height: auto; }
    PlacementConfirmScreen #placement-confirm-keys { height: auto; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-panel"):
            with VerticalScroll():
                yield Static(safe_text(self.message), markup=False, id="confirmation")
            yield Static(
                "y Replace   Esc / n / Enter Cancel",
                markup=False,
                id="placement-confirm-keys",
            )


class ReconcileScreen(ModalScreen[str]):
    """One stable source slot, one focus, and a destination browser."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "place", "Place", priority=True),
        Binding("s", "skip", "Skip", priority=True),
        Binding("u", "undo", "Undo", priority=True),
        Binding("left", "fold('left')", "Close / parent"),
        Binding("right", "fold('right')", "Open / child"),
        Binding("space", "fold('toggle')", "Expand/collapse"),
        Binding("home", "edge(0)", "First", priority=True),
        Binding("end", "edge(-1)", "Last", priority=True),
        Binding("pageup", "page(-1)", "Page up", priority=True),
        Binding("pagedown", "page(1)", "Page down", priority=True),
        Binding("H", "hidden", "Reveal hidden"),
        Binding("question_mark", "details", "Details", priority=True),
        Binding("escape", "back", "Skip remaining", priority=True),
    ]
    DEFAULT_CSS = """
    ReconcileScreen { layout: vertical; background: $surface; padding: 0 1; }
    #relink-source { height: 1; text-style: bold; color: $accent; }
    #relink-divider { height: 1; margin: 0; color: $primary-muted; }
    #relink-tree { height: 1fr; background: $background; }
    #relink-tree ListItem { height: 1; padding: 0; }
    #relink-tree Label { width: 1fr; height: 1; text-wrap: nowrap;
                         text-overflow: ellipsis; }
    #relink-tree .hidden-entry { text-style: dim; }
    #relink-source, #relink-target, #relink-note, #relink-message {
        height: 1; text-wrap: nowrap; text-overflow: ellipsis;
    }
    #relink-target { color: $accent; }
    #relink-note { color: $text; }
    #relink-message { color: $text-muted; }
    #relink-keys { height: auto; background: $surface; }
    """

    def __init__(self, editor: EditorController) -> None:
        super().__init__()
        self.editor = editor
        state = editor.state.reconciliation
        assert state is not None
        self.state = state
        self.session = editor.state.session
        # Browsing has its own expansion and visibility state. Only Place edits
        # the actual draft, revealing the destination so its annotation prints.
        self.browser = TreeSession.restore(self.session.root, self.session.state())
        self.cursor = Cursor(self.browser)
        self.rows: list[tuple[Node, int]] = []
        self.tree_view = ListView(id="relink-tree")
        self.source_widget = Static("", markup=False, id="relink-source")
        self.target_widget = Static("", markup=False, id="relink-target")
        self.note_widget = Static("", markup=False, id="relink-note")
        self.message_widget = Static("", markup=False, id="relink-message")
        self.keys_widget = Static("", markup=False, id="relink-keys")
        self._rebuilding = False

    def compose(self) -> ComposeResult:
        yield self.source_widget
        yield Rule(id="relink-divider")
        yield self.tree_view
        yield self.target_widget
        yield self.note_widget
        yield self.message_widget
        yield self.keys_widget

    async def on_mount(self) -> None:
        await self._refresh(
            "Choose a destination. Folder browsing does not edit the draft."
        )

    def _sync_cursor(self) -> None:
        self.cursor.selected = self.tree_view.index or 0
        self.cursor.move(0)

    def _say(self, message: str) -> None:
        self.message_widget.update(safe_text(message))

    def _source_text(self) -> str:
        source = self.state.current
        if source is None:
            return "Placement finished"
        path = source.path + ("/" if source.is_dir else "")
        return f"[{self.state.remaining} left] From {path}"

    def _row_text(self, node: Node, prefix: str) -> str:
        return safe_text(prefix + row_label(node, self.browser))

    async def _refresh(self, message: str = "") -> None:
        if self.state.current is None:
            self.action_back()
            return
        self._rebuilding = True
        self.browser.annotations = self.session.annotations.copy()
        self.browser.hidden = self.session.hidden.copy()
        self.cursor.move(0)
        self.rows = self.browser.visible_rows()
        try:
            await self.tree_view.clear()
            await self.tree_view.extend(
                ListItem(
                    Label(self._row_text(node, prefix), markup=False),
                    classes="hidden-entry" if self.browser.is_hidden(node.path) else "",
                )
                for (node, _), prefix in zip(
                    self.rows, tree_prefixes(self.rows), strict=True
                )
            )
            self.tree_view.index = self.cursor.selected
        finally:
            self._rebuilding = False
        self.source_widget.update(safe_text(self._source_text()))
        source = self.state.current
        assert source is not None
        note = (
            "# " + source.annotation
            if source.annotation
            else "Matching annotations follow this directory, recursively."
        )
        self.note_widget.update(safe_text(note))
        self.keys_widget.update(self._keys())
        self._show_target()
        self._say(message)
        self.tree_view.focus()

    def _keys(self) -> str:
        return (
            "↑↓ Move  ←→ Folders  Enter Place  s Skip\n"
            "u Undo  H Hidden  ? Details  Esc Skip remaining"
        )

    def _show_target(self) -> None:
        if not self.rows:
            return
        self._sync_cursor()
        node = self.rows[self.cursor.selected][0]
        path = node.path or "."
        if node.is_dir:
            path += "/"
        source = self.state.current
        if source is not None and not source.is_dir and node.is_dir:
            hint = " · → browse folder"
        elif self.browser.is_hidden(node.path):
            hint = " · placing will include this hidden entry"
        else:
            hint = ""
        self.target_widget.update(safe_text("To " + path + hint))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        if not self._rebuilding:
            self._show_target()

    async def action_fold(self, direction: str) -> None:
        self._sync_cursor()
        operation = {
            "left": self.cursor.left,
            "right": self.cursor.right,
            "toggle": self.cursor.toggle,
        }[direction]
        operation()
        await self._refresh()

    def action_edge(self, index: int) -> None:
        self.tree_view.index = index % len(self.rows)

    def action_page(self, direction: int) -> None:
        self._sync_cursor()
        self.cursor.move(direction * max(1, self.tree_view.size.height - 1))
        self.tree_view.index = self.cursor.selected

    async def action_hidden(self) -> None:
        self._sync_cursor()
        message = self.cursor.reveal_hidden()
        await self._refresh(message)

    def _edit(self, operation: Callable[[], object]) -> bool:
        try:
            with self.editor.edit():
                operation()
        except (TreestampError, OSError, ValueError) as exc:
            self._say(f"Draft retained: {exc}")
            return False
        return True

    async def action_place(self) -> None:
        source = self.state.current
        if source is None:
            return
        self._sync_cursor()
        target = self.rows[self.cursor.selected][0]
        if source.is_dir != target.is_dir:
            message = (
                "This annotation belongs on a directory. Choose a folder."
                if source.is_dir
                else "Choose a file. Press → to browse this folder."
            )
            self._say(message)
            return
        question = self.state.conflict(target.path)
        if question:
            self.app.push_screen(
                PlacementConfirmScreen(question),
                partial(self._confirm_place, target.path),
            )
            return
        await self._place(target.path)

    async def _confirm_place(self, destination: str, accepted: bool | None) -> None:
        if accepted:
            await self._place(destination, replace=True)
        else:
            self._say("Replacement cancelled. Choose a destination or skip.")

    async def _place(self, destination: str, *, replace: bool = False) -> None:
        message = ""

        def place() -> None:
            nonlocal message
            message = self.state.place(destination, replace=replace)

        if self._edit(place):
            await self._refresh(message)

    async def action_skip(self) -> None:
        source = self.state.current
        if source is None:
            return
        self.state.skip_current()
        await self._refresh(f"Skipped {source.path}. u undoes.")

    async def action_undo(self) -> None:
        if not self.state.can_undo:
            self._say("No decision to undo.")
            return
        message = ""

        def undo() -> None:
            nonlocal message
            message = self.state.undo()

        if self._edit(undo):
            await self._refresh(message)

    def action_details(self) -> None:
        self._sync_cursor()
        source = self.state.current
        lines = [self._source_text()]
        if source is not None:
            lines.extend(["", "Annotation", source.annotation])
        lines.extend(["", "Destination", self.cursor.path or "."])
        annotation = self.session.annotations.get(self.cursor.path)
        if annotation:
            lines.extend(["", "Current destination annotation", annotation])
        lines.extend(
            [
                "",
                "Enter places the annotation and reveals its destination in the draft.",
                "s skips this item. Skipped annotations are left out when writing.",
                "Directories carry pending annotations at matching relative paths,",
                "including nested paths. Missing or conflicting entries stay queued.",
                "Browsing leaves the saved tree unchanged. H reveals hidden rows.",
                "u undoes the last decision, including a whole directory placement.",
                "Esc skips the remaining items and starts editing without writing.",
            ]
        )
        self.app.push_screen(
            PreviewScreen(
                "Placement details",
                "\n".join(safe_text(line) for line in lines),
                soft_wrap=True,
            )
        )

    def action_back(self) -> None:
        self.dismiss(
            f"Placement finished: {self.state.placed_count} annotations placed, "
            f"{self.state.unplaced} left out. w writes the draft."
        )
