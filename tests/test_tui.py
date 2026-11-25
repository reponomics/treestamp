"""Headless editor journeys preserve navigation and transactional writes."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Input, Static, TextArea

from treestamp.document import parse_document, write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Entry, Node, Settings, build_tree
from treestamp.tui import Cursor, TreestampApp
from treestamp.tui_dialogs import ConfirmScreen, PromptScreen

from .conftest import Repo
from .tui_support import editor_fixture as editor_fixture
from .tui_support import press, prompt, rendered_text


def test_navigation_expands_one_level_collapses_and_moves_to_parent(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert app.cursor.path == ""
            assert rendered_text(app.status_widget) == "Ready to edit a new treestamp."
            assert "unwritten" not in rendered_text(app.summary_widget).lower()
            await press(pilot, "down", "right")
            assert app.cursor.path == "src" and "src" not in app.session.collapsed
            await press(pilot, "right", "right", "right")
            assert app.cursor.path == "src/pkg/leaf"
            await press(pilot, "left", "left")
            assert app.cursor.path == "src/pkg" and "src/pkg" in app.session.collapsed
            await press(pilot, "left", "end")
            assert app.cursor.path == "readme"
            await press(pilot, "home")
            assert app.cursor.path == ""

    asyncio.run(journey())


def test_hide_reveal_restore_and_inspection_dirty_state(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "H")
            assert not app.editor.dirty
            await press(pilot, "H", "down", "h")
            assert app.session.hidden == {"src"}
            assert app.cursor.path == "readme" and app.editor.dirty
            await press(pilot, "H", "up", "h")
            assert not app.session.hidden and not app.editor.dirty
            assert app.cursor.path == "src"

    asyncio.run(journey())


def test_right_does_not_jump_sibling_when_all_children_hidden(
    editor: EditorController,
) -> None:
    session = editor.state.session
    session.expand("src")
    session.hide("src/pkg")
    session.hide("src/main")
    cursor = Cursor(session, selected=1)
    cursor.right()
    assert cursor.path == "src"


def test_show_all_unhides_entries_and_keeps_selection_and_folds(
    editor: EditorController,
) -> None:
    editor.state.session.hide("src")
    editor.state.session.hide("src/pkg/leaf")
    editor.state.session.hidden.add("untracked")

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "end")
            assert app.cursor.path == "readme"
            folds = app.session.collapsed.copy()
            before = app.session.draft_signature()
            assert app.editor.dirty
            await press(pilot, "H")
            assert app.session.draft_signature() == before
            await press(pilot, "S")
            assert not app.session.hidden
            assert app.session.show_hidden
            assert app.session.collapsed == folds
            assert app.cursor.path == "readme"
            assert not app.editor.dirty, "unhiding returns to the original draft"
            assert "All entries included" in rendered_text(app.status_widget)
            after = app.session.draft_signature()
            await press(pilot, "S", "H")
            assert app.session.draft_signature() == after
            assert not app.session.show_hidden
            assert "src" in editor.preview()

    asyncio.run(journey())


def test_annotation_cancel_unicode_and_root_annotation(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            field = await prompt(pilot, "a")
            field.value = "repository 🐍"
            await press(pilot, "enter")
            assert app.session.annotations[""] == "repository 🐍"
            await press(pilot, "down")
            field = await prompt(pilot, "a")
            field.value = "cancelled"
            await press(pilot, "escape")
            assert "src" not in app.session.annotations
            await prompt(pilot, "a")
            text = "a h q p w café 🐍"
            await press(pilot, *text, "enter")
            assert app.session.annotations["src"] == text
            assert not app.session.hidden

    asyncio.run(journey())


def test_dirty_quit_can_cancel_and_revert(editor: EditorController) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "c", "q")
            assert isinstance(app.screen, ConfirmScreen)
            await press(pilot, "n")
            assert app.editor.dirty
            await press(pilot, "c")
            assert not app.editor.dirty
            await press(pilot, "q")
        assert app.return_value is False

    asyncio.run(journey())


def test_new_tree_has_no_write_action_and_keeps_copy_available(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp import tui

    sent: list[str] = []
    monkeypatch.setattr(tui, "_clipboard_command", lambda: None)
    monkeypatch.setattr(
        TreestampApp, "copy_to_clipboard", lambda self, text: sent.append(text)
    )
    editor.state.session.set_annotation("readme", "Copy this note")
    before = editor.state.session.state()

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "w")
            assert len(app.screen_stack) == 1
            assert app.session.state() == before
            assert editor.state.document_path is None
            assert not (editor.state.root / "tree.md").exists()
            assert not (editor.state.root / "README.md").exists()
            controls = "\n".join(
                rendered_text(w)
                for w in app.query(Static).filter(".controls")
                if w.display
            )
            assert "Write" not in controls
            await press(pilot, "?")
            assert "w               " not in app.screen.query_one(TextArea).text
            await press(pilot, "escape", "y")
            assert sent == [editor.region_text()]
            assert "Copy this note" in sent[0]

    asyncio.run(journey())


def test_invalid_annotation_keeps_draft_and_prompt_for_correction(repo: Repo) -> None:
    repo.write("x")
    repo.write("x  # y")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    before = editor.region_text()

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "down")
            field = await prompt(pilot, "a")
            field.value = "invalid\x00note"
            await press(pilot, "enter")
            assert isinstance(app.screen, PromptScreen)
            assert app.screen.query_one(Input).value == "invalid\x00note"
            assert "draft retained" in rendered_text(app.status_widget)
            assert editor.region_text() == before
            assert app.cursor.path == "x"
            app.screen.query_one(Input).value = "y"
            await press(pilot, "enter")
            assert not isinstance(app.screen, PromptScreen)
            assert editor.state.session.annotations["x"] == "y"
            loaded = parse_document(editor.region_text().encode())
            assert {node.path: node.annotation for node in loaded.tree.walk()} == {
                "x": "y",
                "x  # y": "",
            }

    asyncio.run(journey())


def test_rejected_style_change_preserves_draft_and_controls(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp.errors import MarkerError

    before = editor.region_text()
    original = editor.region_text

    def reject(_tree: Node, settings: Settings) -> None:
        if settings.style == "ascii":
            raise MarkerError("injected unsupported style")

    monkeypatch.setattr("treestamp.editor.validate_source_tree", reject)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "s")
            assert app.session.settings.style == "unicode"
            assert "Style: Unicode" in rendered_text(app.summary_widget)
            assert "Attribution: off" in rendered_text(app.summary_widget)
            assert "draft retained" in rendered_text(app.status_widget)
            assert original() == before

    asyncio.run(journey())


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_controls_remain_visible_and_reflect_view_settings(
    editor: EditorController, size: tuple[int, int]
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test(size=size) as pilot:
            assert app.tree_view.size.height >= 5
            for widget in app.query(".controls, #summary"):
                assert widget.region.bottom <= size[1]
                assert widget.virtual_size.width <= size[0]
            assert "Counts: on" in rendered_text(app.summary_widget)
            assert "Style: Unicode" in rendered_text(app.summary_widget)
            await press(pilot, "down", "h", "H", "c", "s", "t")
            assert app.attribution_widget.display
            assert app.attribution_widget.region.bottom <= size[1]
            for widget in app.query(".controls, #summary"):
                assert widget.region.bottom <= size[1]
            summary = rendered_text(app.summary_widget)
            assert "Counts: off" in summary
            assert "Style: ASCII" in summary
            assert "Hidden: shown" in summary
            await press(pilot, "?")
            help_text = app.screen.query_one(TextArea).text
            assert "VIEW AND APPEARANCE" in help_text
            assert "This does not change which entries are printed" in help_text
            await press(pilot, "escape")
            assert app.tree_view.has_focus

    asyncio.run(journey())


def test_count_toggle_without_collapsed_folders_does_not_prompt_on_quit(
    editor: EditorController,
) -> None:
    editor.state.session.expand("src")
    editor.state.session.expand("src/pkg")
    destination = editor.state.root / "tree.md"
    write_document(editor.document(), destination, create=True)
    editor.adopt(editor.prepare_load("tree.md"))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "c")
            assert not app.editor.dirty
            assert "unwritten" not in rendered_text(app.summary_widget).lower()
            await press(pilot, "q")
        assert app.return_value is False

    asyncio.run(journey())


def test_cursor_root_and_leaf_actions_preserve_layout(editor: EditorController) -> None:
    session = editor.state.session
    before = session.state()
    cursor = Cursor(session)
    cursor.left()
    cursor.toggle()
    assert cursor.path == ""
    assert cursor.toggle_hidden() == "The root always stays included."
    cursor.move(100)
    assert cursor.path == "readme"
    cursor.right()
    cursor.toggle()
    assert cursor.path == "readme"
    cursor.left()
    assert cursor.path == ""
    assert session.state() == before


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (Entry("module", "gitlink"), "module/  # submodule"),
        (Entry("link", "symlink", "target\nline"), 'link -> "target\\nline"'),
        (Entry("link", "symlink"), "link -> null"),
    ],
)
def test_special_entry_labels_preserve_type_and_escape_targets(
    entry: Entry, expected: str
) -> None:
    from treestamp.tui_rows import label as _label

    assert _label(build_tree([entry]).children[0]) == expected


def test_page_navigation_clamps_and_dirty_quit_can_be_confirmed(
    editor: EditorController,
) -> None:
    editor.state.session.set_annotation("readme", "unsaved")

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            app.action_page(1)
            assert app.cursor.path == "readme"
            app.action_page(-1)
            assert app.cursor.path == ""
            await press(pilot, "q")
            assert isinstance(app.screen, ConfirmScreen)
            await press(pilot, "y")
        assert app.return_value is False

    asyncio.run(journey())
