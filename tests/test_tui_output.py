"""Editor output, clipboard delivery, and transactional document writes."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from textual.widgets import Static, TextArea

from treestamp.document import ATTRIBUTION, parse_document, write_document
from treestamp.editor import EditorController
from treestamp.gitio import Snapshot
from treestamp.model import Entry, Settings, build_tree
from treestamp.tui import TreestampApp
from treestamp.tui_dialogs import PromptScreen

from .conftest import Repo
from .tui_support import editor_fixture as editor_fixture
from .tui_support import press, prompt, rendered_text


def test_loaded_write_collapse_and_restore_preserve_transient_state(
    editor: EditorController,
) -> None:
    destination = editor.state.root / "tree.md"
    write_document(
        editor.document(), editor.state.snapshot.repo / "tree.md", create=True
    )
    destination.write_text("# Before\n\n" + destination.read_text() + "\nAfter.\n")
    editor.adopt(editor.prepare_load("tree.md"))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "down", "right", "right", "right", "right")
            assert app.cursor.path == "src/pkg/leaf"
            field = await prompt(pilot, "a")
            field.value = "remember me"
            await press(pilot, "enter", "home", "down", "space")
            assert not app.editor.dirty  # hidden annotation is not in the output
            await press(pilot, "w")
            assert not isinstance(app.screen, PromptScreen)
            assert "remember me" not in destination.read_text(encoding="utf-8")
            assert not app.editor.dirty
            await press(pilot, "right")
            assert "remember me" in editor.preview()
            await press(pilot, "w")
            content = destination.read_text(encoding="utf-8")
            assert "remember me" in content and not app.editor.dirty
            assert content.startswith("# Before\n\n") and content.endswith("\nAfter.\n")
            assert app.editor.state.document_path == destination
            await press(pilot, "v")
            assert "remember me" in app.screen.query_one(TextArea).text

    asyncio.run(journey())


def test_conflicting_loaded_write_preserves_dirty_draft(
    editor: EditorController,
) -> None:
    write_document(
        editor.document(), editor.state.snapshot.repo / "tree.md", create=True
    )
    editor.adopt(editor.prepare_load("tree.md"))
    destination = editor.state.root / "tree.md"

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "c")
            before = app.session.state()
            destination.write_text("concurrent changes", encoding="utf-8")
            await press(pilot, "w")
            assert "Write failed" in rendered_text(app.status_widget)
            assert app.editor.dirty
            assert app.session.state() == before
            assert destination.read_text(encoding="utf-8") == "concurrent changes"
            assert not isinstance(app.screen, PromptScreen)

    asyncio.run(journey())


def test_terminal_control_characters_are_escaped(editor: EditorController) -> None:
    tree = build_tree([Entry("strange\n\x1bname")])
    editor = EditorController(
        Snapshot(editor.state.root, editor.state.root, tree, "fixed"), Settings()
    )

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            labels = [
                rendered_text(label)
                for label in app.query(Static).filter("#tree Label")
            ]
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, style: str, dirty: bool, name: str
) -> None:
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


def test_attribution_toggle_loaded_write_and_print(editor: EditorController) -> None:
    write_document(
        editor.document(), editor.state.snapshot.repo / "attributed.md", create=True
    )
    editor.adopt(editor.prepare_load("attributed.md"))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert not app.session.settings.attribution
            assert not app.attribution_widget.display
            await press(pilot, "t")
            assert app.editor.dirty
            assert "Attribution: on" in rendered_text(app.summary_widget)
            assert ATTRIBUTION in app.editor.region_text()
            assert app.attribution_widget.display
            assert "Maintained with treestamp" in rendered_text(app.attribution_widget)
            await press(pilot, "v")
            assert app.screen.query_one(TextArea).text.endswith(f"\n\n{ATTRIBUTION}\n")
            await press(pilot, "escape", "w")
            assert not app.editor.dirty
            saved = parse_document((editor.state.root / "attributed.md").read_bytes())
            assert saved is not None and saved.settings.attribution
            await press(pilot, "t")
            assert ATTRIBUTION not in app.editor.region_text()
            assert not app.attribution_widget.display
            await press(pilot, "v")
            assert ATTRIBUTION not in app.screen.query_one(TextArea).text
            await press(pilot, "escape")
            assert app.editor.dirty
            await press(pilot, "p")
        assert app.return_value is True
        assert ATTRIBUTION not in app.editor.region_text()

    asyncio.run(journey())


def test_open_completion_replaces_generic_unwritten_status(
    editor: EditorController, repo: Repo
) -> None:
    from treestamp.editor import OPEN_UPDATED_NOTICE

    destination = repo.path / "tree.md"
    write_document(editor.document(), destination, create=True)
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
            await press(pilot, "w")
            assert not app.editor.dirty
            assert "Wrote treestamped document" in rendered_text(app.status_widget)

    asyncio.run(journey())


@pytest.mark.parametrize(
    ("platform", "available", "expected"),
    [
        ("darwin", {"pbcopy"}, ["pbcopy"]),
        ("win32", {"clip"}, ["clip"]),
        ("linux", {"wl-copy", "xclip"}, ["wl-copy"]),
        ("linux", {"xclip", "xsel"}, ["xclip", "-selection", "clipboard"]),
        ("linux", {"xsel"}, ["xsel", "--clipboard", "--input"]),
        ("linux", set(), None),
        ("darwin", {"xclip"}, None),
    ],
)
def test_clipboard_selection_respects_platform_and_priority(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    available: set[str],
    expected: list[str] | None,
) -> None:
    from treestamp import tui

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(
        shutil, "which", lambda name: name if name in available else None
    )
    assert tui._clipboard_command() == expected


@pytest.mark.parametrize(
    ("method", "action", "message"),
    [
        ("preview", "action_preview", "Cannot preview tree"),
        ("region_text", "action_copy", "Cannot copy treestamp"),
        ("region_text", "action_print", "Cannot print tree"),
    ],
)
def test_output_failure_keeps_editor_open_and_draft_unchanged(
    editor: EditorController,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    action: str,
    message: str,
) -> None:
    def fail() -> str:
        raise OSError("output unavailable")

    before = editor.state.session.state()
    monkeypatch.setattr(editor, method, fail)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test():
            getattr(app, action)()
            assert rendered_text(app.status_widget) == f"{message}: output unavailable"
            assert len(app.screen_stack) == 1
            assert app.is_running
            assert editor.state.session.state() == before

    asyncio.run(journey())


def test_failed_native_clipboard_reports_error_without_claiming_success(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp import tui

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("clipboard unavailable")

    monkeypatch.setattr(tui, "_clipboard_command", lambda: ["test-clipboard"])
    monkeypatch.setattr(subprocess, "run", fail)
    before = editor.state.session.state()

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test():
            app.action_copy()
            assert (
                rendered_text(app.status_widget)
                == "Cannot copy with test-clipboard: clipboard unavailable"
            )
            assert editor.state.session.state() == before

    asyncio.run(journey())
