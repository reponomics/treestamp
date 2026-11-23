"""Placement navigation and recovery preserve the draft and decision history."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from treestamp.errors import MarkerError
from treestamp.tui import TreestampApp
from treestamp.tui_dialogs import PreviewScreen

from .conftest import Repo
from .test_tui_reconcile import (
    NOTES,
    load_stale,
    opened,
    press,
    selected,
    text_of,
)


def test_navigation_and_empty_undo_leave_draft_and_queue_unchanged(repo: Repo) -> None:
    viewport = (80, 24)
    for index in range(viewport[1] * 2):
        repo.write(f"row_{index}.py")
    editor = load_stale(repo)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test(size=viewport) as pilot:
            screen = await opened(pilot, skip_group=False)
            draft = editor.state.session.state()
            decisions = screen.state.snapshot()
            await press(pilot, "u")
            assert screen.state.snapshot() == decisions
            assert not screen.state.can_undo
            await press(pilot, "down", "space", "end")
            assert selected(screen) == screen.rows[-1][0].path
            # A directory source cannot be placed on a file.
            assert not screen.rows[screen.tree_view.index][0].is_dir
            await press(pilot, "enter")
            assert screen.state.snapshot() == decisions
            await press(pilot, "home")
            assert selected(screen) == screen.rows[0][0].path
            await press(pilot, "pagedown")
            assert 0 < screen.tree_view.index < len(screen.rows) - 1
            await press(pilot, "pageup")
            assert selected(screen) == screen.rows[0][0].path
            await press(pilot, "down")
            assert "pkg/first.py" in [node.path for node, _ in screen.rows]
            await press(pilot, "right", "left")
            assert selected(screen) == "pkg"
            await press(pilot, "left")
            assert "pkg/first.py" not in [node.path for node, _ in screen.rows]
            assert editor.state.session.state() == draft
            assert screen.state.snapshot() == decisions

    asyncio.run(journey())


def test_details_preserves_existing_destination_note_and_selection(repo: Repo) -> None:
    editor = load_stale(repo)
    destination_note = str(uuid4())
    editor.state.session.set_annotation("pkg/existing.py", destination_note)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "right")
            destination = selected(screen)
            draft = editor.state.session.state()
            decisions = screen.state.snapshot()
            await press(pilot, "question_mark")
            assert isinstance(app.screen, PreviewScreen)
            assert destination_note in app.screen.text
            assert NOTES[screen.state.current.path] in app.screen.text
            await press(pilot, "escape")
            assert app.screen is screen
            assert selected(screen) == destination
            assert editor.state.session.state() == draft
            assert screen.state.snapshot() == decisions

    asyncio.run(journey())


@pytest.mark.parametrize("error_type", [MarkerError, OSError, ValueError])
@pytest.mark.parametrize("operation", ["enter", "u"])
def test_failed_edit_restores_draft_and_decisions_and_can_be_retried(
    repo: Repo,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    operation: str,
) -> None:
    editor = load_stale(repo)
    editor.state.session.hide("pkg/first.py")
    failure = str(uuid4())
    saved = repo.read_bytes("tree.md")

    def reject_export() -> None:
        # Export validation happens after placement/undo modifies both the draft
        # and reconciliation history, so failures must roll both back together.
        raise error_type(failure)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "H", "right", "down")
            assert selected(screen) == "pkg/first.py"
            if operation == "u":
                await press(pilot, "enter")
            draft = editor.state.session.state()
            decisions = screen.state.snapshot()
            with monkeypatch.context() as patch:
                patch.setattr(editor, "document", reject_export)
                await press(pilot, operation)
            assert app.screen is screen
            assert screen.tree_view.has_focus
            assert failure in text_of(screen.message_widget)
            assert editor.state.session.state() == draft
            assert screen.state.snapshot() == decisions
            assert repo.read_bytes("tree.md") == saved
            await press(pilot, operation)
            assert screen.state.snapshot() != decisions
            if operation == "enter":
                assert (
                    editor.state.session.annotations["pkg/first.py"]
                    == NOTES["old/a.py"]
                )
                assert not editor.state.session.is_hidden("pkg/first.py")
                assert screen.state.current.path == "old/b.py"
            else:
                assert "pkg/first.py" not in editor.state.session.annotations
                assert editor.state.session.is_hidden("pkg/first.py")
                assert screen.state.current.path == "old/a.py"
            assert repo.read_bytes("tree.md") == saved

    asyncio.run(journey())
