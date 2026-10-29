"""Textual curation against one fixed Git snapshot."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, ClassVar

from textual.app import App
from textual.binding import Binding
from textual.widgets import Label, ListItem, ListView, Static

from treestamp.codec import format_counts
from treestamp.document import ATTRIBUTION_URL, DEFAULT_DOCUMENT_FILE
from treestamp.errors import TreestampError
from treestamp.model import KIND_GITLINK, KIND_SYMLINK
from treestamp.tui_dialogs import (
    ConfirmScreen,
    DocumentChoiceScreen,
    PreviewScreen,
    PromptScreen,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from treestamp.editor import EditorController, EditorState
    from treestamp.model import Node
    from treestamp.session import TreeSession


@dataclass
class Cursor:
    session: TreeSession
    selected: int = 0

    @property
    def path(self) -> str:
        return self.session.visible_rows()[self.selected][0].path

    def move(self, delta: int) -> None:
        self.selected = min(
            max(0, self.selected + delta), len(self.session.visible_rows()) - 1
        )

    def right(self) -> None:
        rows = self.session.visible_rows()
        node, level = rows[self.selected]
        if not node.is_dir:
            return
        if node.path in self.session.collapsed:
            self.session.expand(node.path)
        elif self.selected + 1 < len(rows) and rows[self.selected + 1][1] > level:
            self.move(1)

    def left(self) -> None:
        rows = self.session.visible_rows()
        node, level = rows[self.selected]
        if node.path and node.children and node.path not in self.session.collapsed:
            self.session.collapse(node.path)
            return
        for index in range(self.selected - 1, -1, -1):
            if rows[index][1] < level:
                self.selected = index
                break

    def toggle(self) -> None:
        node, _ = self.session.visible_rows()[self.selected]
        if node.is_dir and node.path:
            self.session.toggle(node.path)

    def repair(self, path: str) -> None:
        """Keep the selected entry, or the nearest surviving row if it vanished."""
        for index, (node, _) in enumerate(self.session.visible_rows()):
            if node.path == path:
                self.selected = index
                return
        self.move(0)

    def toggle_hidden(self) -> str:
        path = self.path
        if not path:
            return "The root always stays included."
        self.session.toggle_hidden(path)
        self.repair(path)
        if self.session.is_hidden(path):
            return f"Hidden: {path} (H reveals hidden entries)"
        return f"Included: {path}"

    def reveal_hidden(self) -> str:
        path = self.path
        self.session.show_hidden = not self.session.show_hidden
        self.repair(path)
        return (
            "Hidden entries revealed for browsing; output is unchanged."
            if self.session.show_hidden
            else "Hidden entries concealed from this view."
        )

    def show_all(self) -> str:
        path = self.path
        self.session.unhide_all()
        self.repair(path)
        return "All entries included; directory expansion is unchanged."


def _label(node: Node) -> str:
    if node.is_dir:
        return f"{node.name}/"
    if node.kind == KIND_GITLINK:
        return f"{node.name}/  # submodule"
    if node.kind == KIND_SYMLINK:
        return f"{node.name} -> {json.dumps(node.target, ensure_ascii=True)}"
    return node.name


def _safe_text(text: str) -> str:
    """Keep paths, annotations, and filesystem errors on one safe terminal row."""
    return "".join(
        json.dumps(char, ensure_ascii=True)[1:-1]
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in text
    )


def _row_label(node: Node, session: TreeSession) -> str:
    closed = node.is_dir and session.is_visibly_collapsed(node.path)
    label = _label(node)
    if closed and session.show_counts:
        files, dirs = session.immediate_counts(node.path)
        counts = format_counts(files, dirs)
        if counts:
            label += " " + counts
    annotation = session.annotations.get(node.path, "")
    if annotation:
        label += f"  # {annotation}"
    return ("[hidden] " if session.is_hidden(node.path) else "") + label


_HELP = (
    "Edit your tree, then write or copy it. Only Write changes files.",
    "",
    "NAVIGATE",
    "Up / Down       Select an entry",
    "Right           Expand a directory or move to its first child",
    "Left            Collapse a directory or move to its parent",
    "Space           Toggle directory expansion",
    "Home / End      First / last row; Page Up / Down scroll",
    "",
    "EDIT",
    "h               Hide or unhide the selected entry",
    "a               Edit the selected entry's annotation",
    "S               Unhide all entries",
    "",
    "VIEW AND APPEARANCE",
    "H               Show or conceal hidden entries in the editor",
    "                This does not change which entries are printed.",
    "c               Show or hide counts on collapsed directories",
    "s               Switch between Unicode, ASCII, and list styles",
    "t               Include or remove the Maintained with treestamp trailer",
    "",
    "DOCUMENT",
    "N               New document: choose a tree root",
    "l               Load document: open and update its draft",
    "n               Write the treestamp to a new file",
    "w               Write the treestamp into an existing document",
    "",
    "OUTPUT",
    "v               Preview the printed tree",
    "y               Copy the complete treestamp",
    "p               Print the complete treestamp and exit",
    "",
    "?               Show this help",
    "q / Esc         Quit; confirm if there are unwritten changes",
    "",
    "Collapse/write/expand preserves curation during this session.",
    "Reopening restores only printed rows and recorded hiding.",
)
STYLES = ("unicode", "ascii", "list")
STYLE_LABELS = {"unicode": "Unicode", "ascii": "ASCII", "list": "List"}
NEW_DESCRIPTION = (
    "Enter a path to the root of the tree, relative to the repository root. "
    "Use . for the repository root (the default)."
)
OPEN_DESCRIPTION = (
    "Opening an existing treestamp will show any updates "
    "based on the current project state. "
    "Document paths are relative to the repository root."
)


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
        Binding("a", "annotate", "Annotate"),
        Binding("c", "counts", "Show counts"),
        Binding("s", "style", "Tree style"),
        Binding("t", "attribution", "Attribution trailer"),
        Binding("N", "new", "New document"),
        Binding("v", "preview", "Preview tree"),
        Binding("y", "copy", "Copy treestamp"),
        Binding("l", "load", "Load document"),
        Binding("n", "create", "Write new file"),
        Binding("w", "document_write", "Write to existing"),
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

    def __init__(
        self, editor: EditorController, *, startup_document: Path | None = None
    ) -> None:
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
        self._rebuilding = False
        self.startup_document = startup_document

    def compose(self) -> ComposeResult:
        yield Static("treestamp", markup=False, id="title")
        yield self.tree_view
        yield self.attribution_widget
        yield self.status_widget
        yield Static(
            "[bold]Tree[/]     ↑↓ Select  ←→ Expand/collapse  Space Toggle  "
            "h Hide/unhide  a Annotate",
            classes="controls",
        )
        yield self.summary_widget
        yield Static(
            "[bold]Document[/] N New  l Load  n Write new file  w Write existing",
            classes="controls",
        )
        yield Static(
            "[bold]Output[/]   v Preview  y Copy  p Print & exit    ? Help  q Quit",
            classes="controls",
        )

    async def on_mount(self) -> None:
        if self.startup_document is None:
            await self.refresh_tree(self.editor.state.status)
        else:
            self._show_startup()

    def _show_startup(self) -> None:
        self.push_screen(DocumentChoiceScreen(), self._accept_startup_choice)

    def _accept_startup_choice(self, operation: str | None) -> None:
        if operation is None:
            self.exit(False)
        else:
            self._prompt_startup(operation)

    def _prompt_startup(
        self, operation: str, value: str | None = None, error: str = ""
    ) -> None:
        new = operation == "new"
        description = NEW_DESCRIPTION if new else OPEN_DESCRIPTION
        self.push_screen(
            PromptScreen(
                "New document" if new else "Load document",
                value
                if value is not None
                else "."
                if new
                else str(self.startup_document),
                description="\n".join(part for part in (description, error) if part),
            ),
            partial(self._accept_startup_input, operation),
        )

    async def _accept_startup_input(self, operation: str, value: str | None) -> None:
        if value is None:
            self._show_startup()
            return
        if value == "":
            self._prompt_startup(operation, value, "Enter a root or document path.")
            return
        try:
            candidate = (
                self.editor.prepare_new(value)
                if operation == "new"
                else self.editor.prepare_load(value)
            )
        except (TreestampError, OSError, ValueError) as exc:
            self._prompt_startup(operation, value, str(exc))
            return
        await self._adopt_editor_state(candidate)

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
        last_children = {
            node.path.rpartition("/")[0]: node.path for node, level in rows if level
        }
        continuations: dict[str, str] = {}
        items: list[ListItem] = []
        for node, level in rows:
            prefix = ""
            continuations[node.path] = ""
            if level:
                parent = node.path.rpartition("/")[0]
                last = last_children[parent] == node.path
                prefix = continuations[parent] + ("└── " if last else "├── ")
                continuations[node.path] = continuations[parent] + (
                    "    " if last else "│   "
                )
            items.append(
                ListItem(
                    Label(
                        _safe_text(prefix + _row_label(node, self.session)),
                        markup=False,
                    ),
                    classes="hidden-entry" if self.session.is_hidden(node.path) else "",
                )
            )
        return items

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
            PromptScreen("Annotation", self.session.annotations.get(path, "")),
            partial(self._accept_annotation, path),
        )

    async def _accept_annotation(self, path: str, value: str | None) -> None:
        if value is None:
            self._set_status("Annotation edit cancelled.")
            return
        accepted, error = self._apply_edit(
            partial(self.session.set_annotation, path, value)
        )
        if not accepted:
            self.push_screen(
                PromptScreen("Annotation", value, description=error),
                partial(self._accept_annotation, path),
            )
            return
        message = (
            "Annotation updated in draft."
            if value.strip()
            else "Annotation removed from draft."
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
        lines = text.count("\n")
        command = _clipboard_command()
        if command is not None:
            try:
                subprocess.run(  # noqa: S603
                    command, input=text.encode("utf-8"), check=True, timeout=5
                )
            except (OSError, subprocess.SubprocessError) as exc:
                self._set_status(f"Cannot copy with {command[0]}: {exc}")
                return
            self._set_status(f"Copied the treestamp ({lines} lines) with {command[0]}.")
            return
        self.copy_to_clipboard(text)
        self._set_status(
            f"Sent the treestamp ({lines} lines) to the terminal's clipboard; "
            "paste to confirm your terminal supports it."
        )

    def action_help(self) -> None:
        self.push_screen(
            PreviewScreen("Keyboard shortcuts", "\n".join(_HELP), soft_wrap=True)
        )

    def _document_default(self, operation: str) -> str:
        state = self.editor.state
        if operation == "create":
            path = state.root / "tree.md"
        else:
            path = state.document_path or state.root / DEFAULT_DOCUMENT_FILE
        return str(path.relative_to(state.snapshot.repo))

    def _prompt_document(self, operation: str) -> None:
        titles = {
            "load": "Load document",
            "create": "Write new file",
            "write": "Write to existing",
        }
        description = (
            OPEN_DESCRIPTION
            if operation == "load"
            else "Document paths are relative to the repository root."
        )
        dialog = PromptScreen(
            titles[operation],
            self._document_default(operation),
            description=description,
        )
        if operation == "load":
            self.push_screen(dialog, self._accept_load)
        else:
            self.push_screen(dialog, partial(self._accept_document_write, operation))

    def action_load(self) -> None:
        self._prompt_document("load")

    def action_new(self) -> None:
        self.push_screen(
            PromptScreen("New document", ".", description=NEW_DESCRIPTION),
            self._accept_new,
        )

    async def _accept_new(self, value: str | None) -> None:
        if value is None or value == "":
            self._set_status("New tree cancelled.")
            return
        try:
            candidate = self.editor.prepare_new(value)
        except (TreestampError, OSError, ValueError) as exc:
            self._set_status(f"New tree failed: {exc}")
            return
        if self.editor.dirty:
            self.push_screen(
                ConfirmScreen("Discard unwritten changes and start a new tree?"),
                partial(self._confirm_load, candidate),
            )
        else:
            await self._adopt_editor_state(candidate)

    def action_create(self) -> None:
        self._prompt_document("create")

    def action_document_write(self) -> None:
        self._prompt_document("write")

    async def _accept_load(self, value: str | None) -> None:
        if value is None or value == "":
            self._set_status("Open cancelled.")
            return
        try:
            candidate = self.editor.prepare_load(value)
        except (TreestampError, OSError, ValueError) as exc:
            self._set_status(f"Open failed: {exc}")
            return
        if self.editor.dirty:
            self.push_screen(
                ConfirmScreen("Discard unwritten changes and open this document?"),
                partial(self._confirm_load, candidate),
            )
        else:
            await self._adopt_editor_state(candidate)

    async def _confirm_load(
        self, candidate: EditorState, confirmed: bool | None
    ) -> None:
        if confirmed:
            await self._adopt_editor_state(candidate)
        else:
            self._set_status("Open cancelled; draft retained.")

    async def _adopt_editor_state(self, candidate: EditorState) -> None:
        self.editor.adopt(candidate)
        self.session = candidate.session
        self.cursor = Cursor(candidate.session)
        await self.refresh_tree(candidate.status)

    async def _accept_document_write(self, operation: str, value: str | None) -> None:
        if value is None or value == "":
            self._set_status("Write cancelled.")
            return
        try:
            write = self.editor.create if operation == "create" else self.editor.write
            message = write(value)
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


def explore(editor: EditorController, *, startup_document: Path) -> bool:
    return bool(TreestampApp(editor, startup_document=startup_document).run())
