"""Textual dialogs used by the tree editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import BindingType


class PromptScreen(ModalScreen[str | None]):
    """Native single-line editing; accepting returns text without writing files."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    PromptScreen { align: center middle; }
    .prompt-panel { width: 90%; max-width: 90; height: auto; padding: 1 2;
                    border: round $accent; background: $surface; }
    .prompt-panel Label { width: 1fr; text-style: bold; margin-bottom: 1; }
    #prompt-description { margin-bottom: 1; }
    .prompt-panel Input { margin-bottom: 1; }
    #prompt-help { color: $text-muted; }
    """

    def __init__(self, title: str, value: str = "", *, description: str = "") -> None:
        super().__init__()
        self.prompt_title = title
        self.initial = value
        self.description = description

    def compose(self) -> ComposeResult:
        with Vertical(classes="prompt-panel"):
            yield Label(self.prompt_title, markup=False)
            if self.description:
                yield Static(self.description, markup=False, id="prompt-description")
            yield Input(self.initial, select_on_focus=False, id="prompt-input")
            yield Static(
                "Enter: accept   Escape: cancel", id="prompt-help", markup=False
            )

    def on_mount(self) -> None:
        field = self.query_one(Input)
        field.focus()
        field.cursor_position = len(field.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y,Y", "accept", "Yes"),
        Binding("n,N,escape,enter", "cancel", "No"),
    ]
    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    .confirm-panel { width: 90%; max-width: 90; height: auto; padding: 1 2;
                     border: round $warning; background: $surface; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="confirm-panel"):
            yield Static(self.message, markup=False, id="confirmation")
            yield Static("y: yes   n / Enter / Escape: no", markup=False)

    def action_accept(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PreviewScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape,q,enter", "close", "Close", priority=True),
        Binding("home", "first", "Top", priority=True),
        Binding("end", "last", "Bottom", priority=True),
    ]
    DEFAULT_CSS = """
    PreviewScreen { align: center middle; }
    .preview-panel { width: 95%; height: 95%; padding: 1;
                     border: round $accent; background: $surface; }
    #preview { height: 1fr; }
    """

    def __init__(self, title: str, text: str, *, soft_wrap: bool = False) -> None:
        super().__init__()
        self.preview_title = title
        self.text = text
        self.soft_wrap = soft_wrap

    def compose(self) -> ComposeResult:
        with Vertical(classes="preview-panel"):
            yield Static(self.preview_title, markup=False)
            yield TextArea(
                self.text,
                read_only=True,
                soft_wrap=self.soft_wrap,
                show_line_numbers=False,
                id="preview",
            )
            yield Static(
                "Arrows/PgUp/PgDn: browse   Home/End: jump   Escape/q/Enter: close",
                markup=False,
            )

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    def action_first(self) -> None:
        self.query_one(TextArea).move_cursor((0, 0))

    def action_last(self) -> None:
        area = self.query_one(TextArea)
        lines = self.text.splitlines() or [""]
        area.move_cursor((len(lines) - 1, len(lines[-1])))

    def action_close(self) -> None:
        self.dismiss(None)
