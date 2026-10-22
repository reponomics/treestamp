"""Headless editor journeys preserve navigation and transactional writes."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Input, Static, TextArea

from treestamp.document import parse_document
from treestamp.editor import EditorController
from treestamp.gitio import Snapshot, capture_snapshot
from treestamp.model import Entry, Settings, build_tree
from treestamp.tui import Cursor, TreestampApp
from treestamp.tui_dialogs import ConfirmScreen, DocumentChoiceScreen, PromptScreen

from .conftest import Repo, run_cli

if TYPE_CHECKING:
    from textual.pilot import Pilot


@pytest.fixture
def editor(repo: Repo) -> EditorController:
    for path in ("src/pkg/leaf", "src/main", "readme"):
        repo.write(path)
    repo.add(".")
    return EditorController(capture_snapshot(repo.path), Settings())


def rendered_text(widget: Static) -> str:
    result = widget.render()
    return getattr(result, "plain", str(result))


async def press(pilot: Pilot[bool], *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


async def prompt(pilot: Pilot[bool], key: str) -> Input:
    await press(pilot, key)
    return pilot.app.screen.query_one("#prompt-input", Input)


@pytest.mark.parametrize("explicit_document", [False, True])
def test_cli_starts_with_choice_and_new_ignores_invalid_existing_document(
    repo: Repo,
    editor: EditorController,
    monkeypatch: pytest.MonkeyPatch,
    explicit_document: bool,
) -> None:
    invalid = "<!-- treestamp:start -->\n<!-- treestamp:end -->\n"
    repo.write("README.md", invalid)
    repo.add("README.md")

    async def journey(app: TreestampApp) -> bool | None:
        async with app.run_test() as pilot:
            assert isinstance(app.screen, DocumentChoiceScreen)
            assert not app.tree_view.children
            assert app.editor.state.document_path is None
            await press(pilot, "n")
            field = app.screen.query_one(Input)
            assert field.value == "."
            description = rendered_text(
                app.screen.query_one("#prompt-description", Static)
            )
            assert "relative to the repository root" in description
            assert "Use . for the repository root (the default)" in description
            field.value = "src"
            await press(pilot, "enter")
            assert not isinstance(app.screen, PromptScreen | ConfirmScreen)
            assert app.session.settings.root == "src"
            assert {node.path for node, _ in app.session.visible_rows()} == {
                "",
                "pkg",
                "main",
            }
            assert not app.editor.dirty
            await press(pilot, "q")
        return app.return_value

    monkeypatch.setattr(TreestampApp, "run", lambda app: asyncio.run(journey(app)))
    arguments = ("--document", "README.md") if explicit_document else ()
    assert run_cli(*arguments) == (0, "", "")
    assert repo.read("README.md") == invalid


def test_startup_load_retries_missing_document_and_opens_without_writing(
    repo: Repo, editor: EditorController
) -> None:
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(editor.state.snapshot.repo)))
    before = destination.read_bytes()
    repo.write("new.txt")
    repo.add("new.txt")
    seed = EditorController(capture_snapshot(repo.path), Settings())

    async def journey() -> None:
        app = TreestampApp(seed, startup_document=destination.relative_to(repo.path))
        async with app.run_test() as pilot:
            await press(pilot, "l")
            field = app.screen.query_one(Input)
            assert field.value == str(
                destination.relative_to(editor.state.snapshot.repo)
            )
            assert "Opening an existing treestamp" in rendered_text(
                app.screen.query_one("#prompt-description", Static)
            )
            field.value = "missing.md"
            await press(pilot, "enter")
            assert isinstance(app.screen, PromptScreen)
            assert "missing.md" in rendered_text(
                app.screen.query_one("#prompt-description", Static)
            )
            app.screen.query_one(Input).value = str(
                destination.relative_to(editor.state.snapshot.repo)
            )
            await press(pilot, "enter")
            assert not isinstance(app.screen, PromptScreen | ConfirmScreen)
            assert app.editor.state.document_path == destination
            assert rendered_text(app.status_widget) == "Treestamp updated"
            assert "new.txt" in app.editor.region_text()
            assert app.editor.dirty
            assert destination.read_bytes() == before

    asyncio.run(journey())


@pytest.mark.parametrize("operation", ["new", "load"])
@pytest.mark.parametrize(
    "name",
    [
        " leading space",
        pytest.param(
            " ",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason="Win32 normalizes whitespace-only path components",
            ),
        ),
    ],
)
def test_startup_preserves_untrimmed_paths(
    repo: Repo, editor: EditorController, operation: str, name: str
) -> None:
    destination = repo.path / name
    if operation == "new":
        repo.write(f"{name}/leaf")
        repo.add(".")
    else:
        editor.create(str(destination.relative_to(editor.state.snapshot.repo)))

    async def journey() -> None:
        app = TreestampApp(editor, startup_document=Path("README.md"))
        async with app.run_test() as pilot:
            await press(pilot, "n" if operation == "new" else "l")
            app.screen.query_one(Input).value = name
            await press(pilot, "enter")
            assert not isinstance(app.screen, PromptScreen)
            if operation == "new":
                assert app.session.settings.root == name
                assert app.editor.state.root == destination
            else:
                assert app.editor.state.document_path == destination
            await press(pilot, "q")
        assert app.return_value is False

    asyncio.run(journey())


def test_startup_input_cancel_returns_to_choice_and_escape_quits(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor, startup_document=Path("README.md"))
        async with app.run_test() as pilot:
            await press(pilot, "n", "escape")
            assert isinstance(app.screen, DocumentChoiceScreen)
            await press(pilot, "l")
            app.screen.query_one(Input).value = ""
            await press(pilot, "enter")
            assert isinstance(app.screen, PromptScreen)
            assert "Enter a root or document path" in rendered_text(
                app.screen.query_one("#prompt-description", Static)
            )
            await press(pilot, "escape", "escape")
        assert app.return_value is False

    asyncio.run(journey())


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


def test_create_write_collapse_and_restore_preserve_transient_state(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "down", "right", "right", "right", "right")
            assert app.cursor.path == "src/pkg/leaf"
            field = await prompt(pilot, "a")
            field.value = "remember me"
            await press(pilot, "enter", "home", "down", "space")
            assert (
                not app.editor.dirty
            )  # annotation is hidden in the unchanged saved tree
            await prompt(pilot, "n")
            await press(pilot, "enter")
            destination = editor.state.root / "tree.md"
            assert destination.exists() and "remember me" not in destination.read_text(
                encoding="utf-8"
            )
            assert not app.editor.dirty
            await press(pilot, "right")
            assert "remember me" in editor.preview()
            field = await prompt(pilot, "w")
            assert field.value == str(
                destination.relative_to(editor.state.snapshot.repo)
            )
            await press(pilot, "enter")
            assert (
                "remember me" in destination.read_text(encoding="utf-8")
                and not app.editor.dirty
            )
            await press(pilot, "v")
            assert "remember me" in app.screen.query_one(TextArea).text

    asyncio.run(journey())


def test_invalid_cancelled_and_conflicting_writes_preserve_dirty_draft(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "c")
            await prompt(pilot, "w")
            await press(pilot, "enter")
            assert "Write failed" in rendered_text(app.status_widget)
            assert app.editor.dirty
            await prompt(pilot, "n")
            await press(pilot, "escape")
            assert app.editor.dirty
            await prompt(pilot, "n")
            await press(pilot, "enter")
            await press(pilot, "c")
            destination = editor.state.root / "tree.md"
            destination.write_text("concurrent changes", encoding="utf-8")
            await prompt(pilot, "w")
            await press(pilot, "enter")
            assert "Write failed" in rendered_text(app.status_widget)
            assert app.editor.dirty
            assert destination.read_text(encoding="utf-8") == "concurrent changes"

    asyncio.run(journey())


def test_load_prepares_before_confirmation_and_cancellation_keeps_draft(
    editor: EditorController,
) -> None:
    destination = editor.state.root / "tree.md"
    editor.create(str(destination.relative_to(editor.state.snapshot.repo)))

    async def journey() -> None:
        app = TreestampApp(editor)
        original_session = app.session
        async with app.run_test() as pilot:
            await press(pilot, "c")
            field = await prompt(pilot, "l")
            field.value = str(destination.relative_to(editor.state.snapshot.repo))
            await press(pilot, "enter")
            assert isinstance(app.screen, ConfirmScreen)
            await press(pilot, "n")
            assert app.session is original_session and app.editor.dirty
            await prompt(pilot, "l")
            await press(pilot, "enter", "y")
            assert app.session is not original_session and not app.editor.dirty
            assert app.cursor.path == ""

    asyncio.run(journey())


def test_terminal_control_characters_are_escaped(editor: EditorController) -> None:
    tree = build_tree([Entry("strange\n\x1bname")])
    editor = EditorController(
        Snapshot(editor.state.root, editor.state.root, tree, "fixed"), Settings()
    )

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            labels = [rendered_text(label) for label in app.query("#tree Label")]
            assert any(r"strange\n\u001bname" in label for label in labels)
            await press(pilot, "down", "h")
            status = rendered_text(app.status_widget)
            assert r"strange\n\u001bname" in status
            assert "\n" not in status and "\x1b" not in status

    asyncio.run(journey())


def test_print_exits_without_writing(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "p")
        assert app.return_value is True
        assert not (editor.state.root / "tree.md").exists()

    asyncio.run(journey())


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize("dirty", [False, True])
@pytest.mark.parametrize("name", ["notes  # draft.md", "notes.md"])
def test_copy_uses_a_native_tool_or_the_terminal(
    tmp_path: Path, monkeypatch, style: str, dirty: bool, name: str
) -> None:
    import sys

    from treestamp import tui

    tree = build_tree([Entry(name), Entry("readme")])
    editor = EditorController(
        Snapshot(tmp_path, tmp_path, tree, "fixed"),
        Settings(style=style),
    )
    if dirty:
        editor.state.session.set_annotation(name, "Working # notes ## unchanged")
    before = editor.state.session.draft_signature()
    sink = tmp_path / "clipboard.txt"
    script = tmp_path / "copytool.py"
    script.write_text(
        f"import sys; open({str(sink)!r}, 'wb').write(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        tui, "_clipboard_command", lambda: [sys.executable, str(script)]
    )

    async def native() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "y")
            assert "Copied the treestamp" in rendered_text(app.status_widget)
            assert app.editor.dirty is dirty
        # Bytes, not text: the clipboard tool is handed what the paste will carry,
        # and reading this back as text would hide a carriage return on Windows.
        assert sink.read_bytes() == editor.region_text().encode("utf-8")
        assert b"\r\n" not in sink.read_bytes()
        copied = parse_document(sink.read_bytes())
        assert copied is not None
        assert copied.tree == editor.document().tree
        assert ("special_paths" in sink.read_text(encoding="utf-8")) is ("  # " in name)

    asyncio.run(native())

    sent: list[str] = []
    monkeypatch.setattr(tui, "_clipboard_command", lambda: None)
    monkeypatch.setattr(
        TreestampApp, "copy_to_clipboard", lambda self, text: sent.append(text)
    )

    async def terminal() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "y")
            assert "terminal's clipboard" in rendered_text(app.status_widget)
            assert app.editor.dirty is dirty
        assert sent == [editor.region_text()]
        assert parse_document(sent[0].encode()) == parse_document(sink.read_bytes())

    asyncio.run(terminal())
    assert not (tmp_path / "tree.md").exists()
    assert editor.state.document_path is None
    assert editor.state.session.draft_signature() == before


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
            field.value = "y"
            await press(pilot, "enter")
            assert isinstance(app.screen, PromptScreen)
            assert app.screen.query_one(Input).value == "y"
            assert "draft retained" in rendered_text(app.status_widget)
            assert editor.region_text() == before
            assert app.cursor.path == "x"
            app.screen.query_one(Input).value = "valid note"
            await press(pilot, "enter")
            assert not isinstance(app.screen, PromptScreen)
            assert editor.state.session.annotations["x"] == "valid note"

    asyncio.run(journey())


def test_rejected_style_change_preserves_draft_and_controls(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp.errors import MarkerError

    before = editor.region_text()
    original = editor.region_text

    def reject(_tree, settings):
        if settings.style == "ascii":
            raise MarkerError("injected unsupported style")

    monkeypatch.setattr("treestamp.editor.validate_source_tree", reject)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "s")
            assert app.session.settings.style == "unicode"
            assert "Style: Unicode" in rendered_text(app.summary_widget)
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
            await press(pilot, "down", "h", "H", "c", "s")
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


def test_new_root_and_style_controls(editor: EditorController) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "s")
            assert app.session.settings.style == "ascii" and app.editor.dirty
            field = await prompt(pilot, "N")
            field.value = "src"
            await press(pilot, "enter")
            assert isinstance(app.screen, ConfirmScreen)
            await press(pilot, "n")
            assert app.session.settings.root == "."
            field = await prompt(pilot, "N")
            field.value = "src"
            await press(pilot, "enter", "y")
            assert app.session.settings.root == "src"
            assert app.session.settings.style == "unicode"
            assert app.cursor.path == "" and not app.editor.dirty
            assert "pkg" in app.session.collapsed
            field = await prompt(pilot, "N")
            field.value = "../outside"
            await press(pilot, "enter")
            assert "New tree failed" in rendered_text(app.status_widget)
            assert app.session.settings.root == "src"
            await prompt(pilot, "N")
            await press(pilot, "escape")
            assert "cancelled" in rendered_text(app.status_widget)

    asyncio.run(journey())


def test_open_completion_replaces_generic_unwritten_status(
    editor: EditorController, repo: Repo
) -> None:
    from treestamp.editor import OPEN_UPDATED_NOTICE

    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(editor.state.snapshot.repo)))
    repo.write("new.txt")
    repo.add("new.txt")
    editor.adopt(
        editor.prepare_load(str(destination.relative_to(editor.state.snapshot.repo)))
    )
    before = destination.read_bytes()

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert OPEN_UPDATED_NOTICE in rendered_text(app.status_widget)
            assert "unwritten" not in rendered_text(app.summary_widget).lower()
            assert app.editor.dirty
            assert destination.read_bytes() == before
            await press(pilot, "down")
            assert OPEN_UPDATED_NOTICE not in rendered_text(app.status_widget)
            await prompt(pilot, "w")
            await press(pilot, "enter")
            assert not app.editor.dirty
            await prompt(pilot, "l")
            assert rendered_text(
                app.screen.query_one("#prompt-description", Static)
            ) == (
                "Opening an existing treestamp will show any updates "
                "based on the current project state. "
                "Document paths are relative to the repository root."
            )
            await press(pilot, "enter")
            assert rendered_text(app.status_widget) == "Treestamp is up to date"
            assert not app.editor.dirty

    asyncio.run(journey())


def test_count_toggle_without_collapsed_folders_does_not_prompt_on_quit(
    editor: EditorController,
) -> None:
    editor.state.session.expand("src")
    editor.state.session.expand("src/pkg")
    destination = editor.state.root / "tree.md"
    editor.create(str(destination.relative_to(editor.state.snapshot.repo)))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "c")
            assert not app.editor.dirty
            assert "unwritten" not in rendered_text(app.summary_widget).lower()
            await press(pilot, "q")
        assert app.return_value is False

    asyncio.run(journey())
