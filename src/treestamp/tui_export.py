"""Save standalone SVG copies without adopting a destination as the source."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from treestamp.artifacts import capture_export_destination
from treestamp.document import publish_write
from treestamp.errors import TreestampError
from treestamp.gitio import document_path
from treestamp.tui_dialogs import ConfirmScreen
from treestamp.tui_rows import safe_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult
    from textual.binding import BindingType

    from treestamp.document import PreparedWrite
    from treestamp.editor import EditorController


class SvgExportScreen(ModalScreen[str | None]):
    """A failed save or copy retains both the dialog and entered destination."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    SvgExportScreen { align: center middle; }
    #svg-export-panel { width: 90%; max-width: 90; height: auto; max-height: 95%;
                        overflow-y: auto; padding: 1 2; border: round $accent;
                        background: $surface; }
    #svg-export-panel Static { height: auto; margin-bottom: 1; }
    #svg-export-path { margin-bottom: 1; }
    #svg-export-actions { height: auto; }
    #svg-export-actions Button { min-width: 10; width: 1fr; }
    #svg-export-error { color: $warning; }
    """

    def __init__(
        self, editor: EditorController, copy: Callable[[str, str], str]
    ) -> None:
        super().__init__()
        self.editor = editor
        self.copy_svg = copy
        suggested = editor.state.snapshot.repo / "treestamp.svg"
        self.initial = (
            "" if suggested == editor.state.document_path else "treestamp.svg"
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="svg-export-panel"):
            appearance = self.editor.state.svg_appearance
            yield Static(
                f"Export SVG — {appearance.theme}, {appearance.style}", markup=False
            )
            yield Static(
                "Graphical preview is unavailable here. "
                "View the saved SVG in a browser. "
                "Add its README image reference manually.",
                markup=False,
            )
            yield Static(
                "Save a separate .svg file in this repository. "
                "Use Write to document to update the loaded source.",
                markup=False,
            )
            yield Input(
                self.initial,
                placeholder="Repository-relative SVG path",
                id="svg-export-path",
            )
            yield Static("", markup=False, id="svg-export-error")
            with Horizontal(id="svg-export-actions"):
                yield Button("Save SVG", variant="primary", id="svg-export-save")
                yield Button("Copy SVG", id="svg-export-copy")
                yield Button("Cancel", id="svg-export-cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def show_error(self, message: str) -> None:
        self.query_one("#svg-export-error", Static).update(safe_text(message))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "svg-export-save":
            self.save()
        elif event.button.id == "svg-export-copy":
            self.copy()
        else:
            self.action_cancel()

    def save(self) -> None:
        path = self.query_one(Input).value
        try:
            repository = self.editor.state.snapshot.repo
            destination = document_path(repository, path)
            previous = capture_export_destination(
                destination,
                repository=repository,
                source=self.editor.state.document_path,
            )
            prepared = self.editor.prepare_svg_export(path, expected=previous)
        except (TreestampError, OSError, ValueError) as exc:
            self.show_error(f"Cannot save SVG: {exc}")
            return
        if previous is not None:
            self.app.push_screen(
                ConfirmScreen(
                    f"Replace existing SVG file {safe_text(str(destination))}?"
                ),
                partial(self.confirm_replace, prepared),
            )
        else:
            self.publish(prepared)

    def confirm_replace(self, prepared: PreparedWrite, accepted: bool | None) -> None:
        if accepted:
            self.publish(prepared)
        else:
            self.show_error("Replacement cancelled; no file written.")

    def publish(self, prepared: PreparedWrite) -> None:
        try:
            saved = publish_write(prepared)
        except (TreestampError, OSError, ValueError) as exc:
            self.show_error(f"Cannot save SVG: {exc}")
            return
        self.dismiss(
            f"Saved SVG: {saved.path}. Add the README image reference manually."
        )

    def copy(self) -> None:
        try:
            message = self.copy_svg(self.editor.svg_text(), "SVG source")
        except (TreestampError, OSError, ValueError) as exc:
            self.show_error(f"{exc}. Save SVG is also available.")
            return
        self.dismiss(message)

    def action_cancel(self) -> None:
        self.dismiss(None)
