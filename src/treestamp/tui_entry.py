"""Choose a working-tree folder or document before opening an editor session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from treestamp.editor import EditorState
from treestamp.errors import TreestampError
from treestamp.tui_rows import safe_text

if TYPE_CHECKING:
    from pathlib import Path

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from treestamp.editor import EditorController


@dataclass(frozen=True)
class SourceRow:
    path: Path
    kind: str
    depth: int
    prefix: str = ""


def source_kind(path: Path) -> str:
    """Links are visible but never followed or accepted as a source."""
    if path.is_symlink():
        return "link"
    if path.is_dir():
        return "dir"
    return "file" if path.is_file() else "other"


class SourceChoiceScreen(ModalScreen[EditorState | None]):
    """Browse the filesystem without changing or preflighting a draft."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "activate", "Choose", priority=True),
        Binding("left", "fold('left')", "Close / parent"),
        Binding("right", "fold('right')", "Open / child"),
        Binding("space", "fold('toggle')", "Expand/collapse", priority=True),
        Binding("home", "edge(0)", "First", priority=True),
        Binding("end", "edge(-1)", "Last", priority=True),
        Binding("pageup", "page(-1)", "Page up", priority=True),
        Binding("pagedown", "page(1)", "Page down", priority=True),
        Binding("q,escape", "quit", "Quit", priority=True),
    ]
    DEFAULT_CSS = """
    SourceChoiceScreen { layout: vertical; background: $background; padding: 0 1; }
    #source-heading { height: 1; text-style: bold; }
    #source-repository { height: 1; color: $text-muted; }
    #source-tree { height: 1fr; min-height: 3; background: $surface; }
    #source-tree ListItem { height: 1; padding: 0; }
    #source-tree Label { height: 1; width: 1fr; text-wrap: nowrap;
                         text-overflow: ellipsis; }
    #source-selection { height: auto; max-height: 2; }
    #source-error { height: auto; max-height: 3; color: $warning; }
    #source-actions { height: 3; }
    #source-open { width: 1fr; min-width: 0; height: 3; }
    #source-folder { width: 12; min-width: 12; height: 3; }
    #source-help { height: auto; color: $text-muted; }
    """

    def __init__(self, editor: EditorController) -> None:
        super().__init__()
        self.editor = editor
        self.repository = editor.state.snapshot.repo
        self.expanded = {self.repository}
        self.rows: list[SourceRow] = []
        self.source_tree = ListView(id="source-tree")
        self.selection = Static("", markup=False, id="source-selection")
        self.error = Static("", markup=False, id="source-error")
        self.open_button = Button("Create treestamp here", id="source-open")
        self.folder_button = Button("Expand", id="source-folder")
        self._rebuilding = False
        self._error_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Static("Where would you like to start?", id="source-heading")
        yield Static(
            safe_text(str(self.repository)), markup=False, id="source-repository"
        )
        yield self.source_tree
        yield self.selection
        yield self.error
        with Horizontal(id="source-actions"):
            yield self.folder_button
            yield self.open_button
        yield Static(
            "↑↓ Select  ←→ Folders\nEnter Choose  Esc/q Quit",
            markup=False,
            id="source-help",
        )

    async def on_mount(self) -> None:
        await self.refresh_sources(self.repository)

    def directory_entries(self, path: Path) -> list[tuple[Path, str]]:
        try:
            entries = [
                (item, source_kind(item))
                for item in path.iterdir()
                if item.name != ".git"
            ]
        except OSError as exc:
            self.show_error(path, f"Cannot browse this folder: {exc}")
            return []
        return sorted(entries, key=lambda item: (item[1] != "dir", item[0].name))

    def collect(self, path: Path, depth: int = 0, prefix: str = "") -> list[SourceRow]:
        if path not in self.expanded:
            return []
        children = self.directory_entries(path)
        rows = []
        for index, (child, kind) in enumerate(children):
            last = index == len(children) - 1
            rows.append(
                SourceRow(child, kind, depth + 1, prefix + ("└── " if last else "├── "))
            )
            if kind == "dir":
                rows.extend(
                    self.collect(
                        child, depth + 1, prefix + ("    " if last else "│   ")
                    )
                )
        return rows

    async def refresh_sources(self, selected: Path) -> None:
        self._rebuilding = True
        self.rows = [
            SourceRow(self.repository, "dir", 0),
            *self.collect(self.repository),
        ]
        try:
            await self.source_tree.clear()
            await self.source_tree.extend(
                ListItem(Label(self.label(row), markup=False)) for row in self.rows
            )
            self.source_tree.index = next(
                (i for i, row in enumerate(self.rows) if row.path == selected), 0
            )
        finally:
            self._rebuilding = False
        self.show_selection()
        self.source_tree.focus()

    def label(self, row: SourceRow) -> str:
        name = (
            "./"
            if row.depth == 0
            else row.path.name + ("/" if row.kind == "dir" else "")
        )
        suffix = " [symlink]" if row.kind == "link" else ""
        return safe_text(row.prefix + name + suffix)

    @property
    def current(self) -> SourceRow:
        return self.rows[self.source_tree.index or 0]

    def show_selection(self) -> None:
        row = self.current
        relative = row.path.relative_to(self.repository).as_posix()
        self.selection.update(safe_text(relative + ("/" if row.kind == "dir" else "")))
        self.open_button.label = (
            "Create treestamp here"
            if row.kind == "dir"
            else "Load treestamp from document"
        )
        self.open_button.disabled = row.kind not in {"dir", "file"}
        self.folder_button.display = row.kind == "dir" and row.path != self.repository
        self.folder_button.label = "Collapse" if row.path in self.expanded else "Expand"

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        if not self._rebuilding and self.rows:
            if self.current.path != self._error_path:
                self.error.update("")
            self.show_selection()

    async def action_fold(self, direction: str) -> None:
        row = self.current
        self.error.update("")
        if direction == "left":
            if row.path != self.repository and row.path in self.expanded:
                self.expanded.remove(row.path)
                await self.refresh_sources(row.path)
            else:
                self.select_parent(row)
        elif row.kind == "dir":
            await self.open_or_toggle(row, direction)

    def select_parent(self, row: SourceRow) -> None:
        self.source_tree.index = next(
            (i for i, item in enumerate(self.rows) if item.path == row.path.parent), 0
        )
        self.source_tree.focus()

    async def open_or_toggle(self, row: SourceRow, direction: str) -> None:
        if row.path not in self.expanded:
            self.expanded.add(row.path)
            await self.refresh_sources(row.path)
        elif direction == "toggle" and row.path != self.repository:
            self.expanded.remove(row.path)
            await self.refresh_sources(row.path)
        elif direction == "right":
            index = self.source_tree.index or 0
            if index + 1 < len(self.rows) and self.rows[index + 1].depth > row.depth:
                self.source_tree.index = index + 1

    def action_edge(self, index: int) -> None:
        self.source_tree.index = index % len(self.rows)

    def action_page(self, direction: int) -> None:
        index = (self.source_tree.index or 0) + direction * max(
            1, self.source_tree.size.height - 1
        )
        self.source_tree.index = min(max(index, 0), len(self.rows) - 1)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button is self.folder_button:
            await self.action_fold("toggle")
        else:
            await self.action_accept()

    async def action_activate(self) -> None:
        if self.app.focused is self.folder_button:
            await self.action_fold("toggle")
        else:
            await self.action_accept()

    async def action_accept(self) -> None:
        row = self.current
        if row.kind not in {"dir", "file"}:
            self.show_error(
                row.path,
                "Choose a folder or regular document; symbolic links cannot be opened.",
            )
            return
        relative = row.path.relative_to(self.repository).as_posix()
        try:
            candidate = (
                self.editor.prepare_new(relative)
                if row.kind == "dir"
                else self.editor.prepare_load(relative)
            )
        except (TreestampError, OSError, ValueError) as exc:
            self.show_error(row.path, str(exc))
            self.source_tree.focus()
            return
        self.dismiss(candidate)

    def show_error(self, path: Path, message: str) -> None:
        self._error_path = path
        self.error.update(safe_text(message))

    def action_quit(self) -> None:
        self.dismiss(None)
